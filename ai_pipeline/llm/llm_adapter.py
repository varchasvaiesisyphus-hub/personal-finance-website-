"""
ai_pipeline/llm/llm_adapter.py

Pluggable LLM adapter layer.
- MockAdapter    : deterministic, offline, for tests
- ClaudeAdapter  : Anthropic Claude via HTTP
- GeminiAdapter  : Google Gemini via HTTP  ← NEW
- OpenAIAdapter  : stub

Env vars
--------
LLM_PROVIDER          mock | claude | gemini   (default: mock)
CLAUDE_API_KEY        required for claude
GEMINI_API_KEY        required for gemini
LLM_MODEL             overrides default model for whichever adapter is active
LLM_TIMEOUT_SECONDS   request timeout (default 60)
LLM_RETRY_MAX         retry attempts   (default 3)
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


def _get_retry_max() -> int:
    return int(os.environ.get("LLM_RETRY_MAX", 3))


def _get_timeout() -> int:
    return int(os.environ.get("LLM_TIMEOUT_SECONDS", 60))


# ─────────────────────────────────────────────────────────────────────────────
# Protocol
# ─────────────────────────────────────────────────────────────────────────────

@runtime_checkable
class LLMAdapter(Protocol):
    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str: ...


# ─────────────────────────────────────────────────────────────────────────────
# MockAdapter
# ─────────────────────────────────────────────────────────────────────────────

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
    """Offline adapter for tests — ignores prompt, returns fixed JSON."""

    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str:
        logger.debug("MockAdapter.generate called")
        return _MOCK_RESPONSE


# ─────────────────────────────────────────────────────────────────────────────
# ClaudeAdapter
# ─────────────────────────────────────────────────────────────────────────────

_CLAUDE_API_URL   = "https://api.anthropic.com/v1/messages"
_CLAUDE_DEFAULT_MODEL = "claude-3-haiku-20240307"


class ClaudeAdapter:
    def __init__(self) -> None:
        self.api_key = os.environ.get("CLAUDE_API_KEY", "")
        self.model   = os.environ.get("LLM_MODEL", _CLAUDE_DEFAULT_MODEL)
        if not self.api_key:
            raise EnvironmentError("CLAUDE_API_KEY is required when LLM_PROVIDER=claude")

    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str:
        logger.debug("ClaudeAdapter.generate — model=%s", self.model)

        @retry(
            retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            stop=stop_after_attempt(_get_retry_max()),
            reraise=True,
        )
        def _call() -> str:
            response = requests.post(
                _CLAUDE_API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=_get_timeout(),
            )
            response.raise_for_status()
            return response.json()["content"][0]["text"]

        return _call()


# ─────────────────────────────────────────────────────────────────────────────
# GeminiAdapter  ← NEW
# ─────────────────────────────────────────────────────────────────────────────

_GEMINI_DEFAULT_MODEL = "gemini-2.0-flash"
_GEMINI_API_BASE      = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiAdapter:
    """
    Calls Google Gemini via the REST generateContent endpoint.

    Env vars:
        GEMINI_API_KEY   — required
        LLM_MODEL        — overrides default (gemini-1.5-flash)
    """

    def __init__(self) -> None:
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.model   = os.environ.get("LLM_MODEL", _GEMINI_DEFAULT_MODEL)
        if not self.api_key:
            raise EnvironmentError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")

    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str:
        logger.debug("GeminiAdapter.generate — model=%s", self.model)

        url = f"{_GEMINI_API_BASE}/{self.model}:generateContent?key={self.api_key}"

        @retry(
            retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            stop=stop_after_attempt(_get_retry_max()),
            reraise=True,
        )
        def _call() -> str:
            response = requests.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature":     temperature,
                        "maxOutputTokens": max_tokens,
                        # Disable thinking so all tokens go to actual output
                        "thinkingConfig": {"thinkingBudget": 0},
                    },
                },
                timeout=120,  # generous — large prompts need time
            )
            response.raise_for_status()
            data = response.json()
            # Gemini response shape: candidates[0].content.parts[0].text
            try:
                text = data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError) as exc:
                raise RuntimeError(f"Unexpected Gemini response shape: {data}") from exc
            logger.debug("GeminiAdapter response preview: %s", text[:300])
            return text

        return _call()


# ─────────────────────────────────────────────────────────────────────────────
# OpenAIAdapter stub
# ─────────────────────────────────────────────────────────────────────────────

class OpenAIAdapter:
    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str:
        raise NotImplementedError("OpenAIAdapter is a stub. Use LLM_PROVIDER=mock|claude|gemini.")