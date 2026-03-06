"""
ai_pipeline/llm/llm_adapter.py

Pluggable LLM adapter layer.
- LLMAdapter: typed Protocol that all adapters must satisfy.
- MockAdapter: deterministic, offline adapter for tests.
- ClaudeAdapter: HTTP-based adapter for Anthropic Claude.
  (Swap the requests call for the Anthropic SDK if preferred.)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Protocol, runtime_checkable

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Protocol
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class LLMAdapter(Protocol):
    """All adapters must implement this single method."""

    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """
        Send *prompt* to the LLM and return the raw response string.

        Args:
            prompt: The fully-built prompt string.
            temperature: Sampling temperature (≤ 0.3 for deterministic output).
            max_tokens: Maximum tokens to generate.

        Returns:
            Raw text response from the model.

        Raises:
            RuntimeError: After all retries are exhausted for network adapters.
        """
        ...


# ─────────────────────────────────────────────────────────────────────────────
# MockAdapter — deterministic, zero-network, for tests
# ─────────────────────────────────────────────────────────────────────────────

# Fixed response that always passes parser validation.
_MOCK_RESPONSE: str = json.dumps({
    "suggestions": [
        {
            "action": "Reduce dining out expenses",
            "explanation": (
                "Your food & dining category shows consistently high spend. "
                "Cooking at home 3 extra days per week could yield meaningful savings."
            ),
            "estimated_monthly_saving_in_inr": 2000.0,
            "confidence": "high",
            "next_step": "Track every restaurant visit for 2 weeks to identify patterns.",
            "tags": ["food", "dining", "savings"],
        },
        {
            "action": "Cancel unused subscriptions",
            "explanation": (
                "Recurring charges detected for multiple streaming services. "
                "Review which ones you actively use."
            ),
            "estimated_monthly_saving_in_inr": 800.0,
            "confidence": "medium",
            "next_step": "List all active subscriptions and cancel at least one.",
            "tags": ["subscriptions", "recurring", "entertainment"],
        },
    ]
})


class MockAdapter:
    """
    Offline adapter that returns a fixed, schema-valid JSON string.
    Used exclusively for unit tests — no network calls, no API keys required.
    """

    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str:  # noqa: ARG002
        logger.debug("MockAdapter.generate called (prompt preview: %s)", prompt[:300])
        return _MOCK_RESPONSE


# ─────────────────────────────────────────────────────────────────────────────
# ClaudeAdapter — Anthropic Claude via HTTP
# ─────────────────────────────────────────────────────────────────────────────

# Env-var defaults
_CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
_DEFAULT_MODEL = "claude-3-haiku-20240307"
_DEFAULT_TIMEOUT = 60
_DEFAULT_RETRY_MAX = 3


def _get_retry_max() -> int:
    return int(os.environ.get("LLM_RETRY_MAX", _DEFAULT_RETRY_MAX))


def _get_timeout() -> int:
    return int(os.environ.get("LLM_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT))


class ClaudeAdapter:
    """
    Calls the Anthropic Claude API via raw HTTP (requests).

    Swap for Anthropic SDK if preferred:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        message = client.messages.create(...)

    Reads from env vars:
        CLAUDE_API_KEY  — required when using this adapter
        LLM_MODEL       — model string (default: claude-3-haiku-20240307)
        LLM_TIMEOUT_SECONDS — request timeout (default: 60)
        LLM_RETRY_MAX   — max retry attempts (default: 3)
    """

    def __init__(self) -> None:
        self.api_key: str = os.environ.get("CLAUDE_API_KEY", "")
        self.model: str = os.environ.get("LLM_MODEL", _DEFAULT_MODEL)
        if not self.api_key:
            raise EnvironmentError(
                "CLAUDE_API_KEY env var is required when LLM_PROVIDER=claude"
            )

    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str:
        """Call Claude and return the assistant's text content."""
        logger.debug("ClaudeAdapter prompt preview: %s", prompt[:300])

        # Build a retry-decorated inner call so retry_max can be read at call time.
        @retry(
            retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            stop=stop_after_attempt(_get_retry_max()),
            reraise=True,
        )
        def _call() -> str:
            # --- swap for Anthropic SDK if preferred ---
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            body = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            response = requests.post(
                _CLAUDE_API_URL,
                headers=headers,
                json=body,
                timeout=_get_timeout(),
            )
            response.raise_for_status()
            data = response.json()
            text: str = data["content"][0]["text"]
            logger.debug("ClaudeAdapter response preview: %s", text[:300])
            return text

        return _call()


# ─────────────────────────────────────────────────────────────────────────────
# OpenAIAdapter stub — not implemented, included for extensibility
# ─────────────────────────────────────────────────────────────────────────────

class OpenAIAdapter:
    """
    Stub for an OpenAI-compatible adapter.
    Not implemented — set LLM_PROVIDER=openai only after filling this in.
    """

    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str:  # noqa: ARG002
        raise NotImplementedError(
            "OpenAIAdapter is a stub. Implement it or use LLM_PROVIDER=mock|claude."
        )