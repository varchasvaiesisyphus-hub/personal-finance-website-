"""
ai_pipeline/llm/llm_adapter.py

BUG 9 FIX:  GeminiAdapter added with thinkingConfig INSIDE generationConfig.
BUG 1 FIX:  get_adapter() is in insights.py — this file just exports GeminiAdapter.
BUG 11 FIX: GeminiAdapter now skips thought parts (Gemini 2.5+ thinking output).

Gemini 2.5 Flash (and Pro) return thinking tokens as a separate part in the
response with {"thought": True} before the actual answer part.  The old code
blindly took parts[0]["text"], which is the raw internal monologue — full of
partial JSON fragments and unbalanced braces — causing parse_llm_response to
crash with "Unbalanced braces in LLM response."

Fix: iterate parts, skip any with thought=True, use the first real text part.
"""
from __future__ import annotations
import json, logging, os
from typing import Protocol, runtime_checkable
import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMAdapter(Protocol):
    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str: ...


# ── MockAdapter ──────────────────────────────────────────────────────────────

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
    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str:
        logger.debug("MockAdapter.generate called")
        return _MOCK_RESPONSE


# ── ClaudeAdapter ────────────────────────────────────────────────────────────

_CLAUDE_API_URL   = "https://api.anthropic.com/v1/messages"
_CLAUDE_DEFAULT   = "claude-3-haiku-20240307"
_DEFAULT_TIMEOUT  = 60
_DEFAULT_RETRY    = 3


class ClaudeAdapter:
    def __init__(self) -> None:
        self.api_key = os.environ.get("CLAUDE_API_KEY", "")
        self.model   = os.environ.get("LLM_MODEL", _CLAUDE_DEFAULT)
        if not self.api_key:
            raise EnvironmentError("CLAUDE_API_KEY env var is required when LLM_PROVIDER=claude")

    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str:
        timeout   = int(os.environ.get("LLM_TIMEOUT_SECONDS", _DEFAULT_TIMEOUT))
        retry_max = int(os.environ.get("LLM_RETRY_MAX", _DEFAULT_RETRY))

        @retry(
            retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            stop=stop_after_attempt(retry_max),
            reraise=True,
        )
        def _call() -> str:
            headers = {
                "x-api-key":         self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            }
            body = {
                "model":       self.model,
                "max_tokens":  max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            response = requests.post(_CLAUDE_API_URL, headers=headers, json=body, timeout=timeout)
            response.raise_for_status()
            return response.json()["content"][0]["text"]

        return _call()


# ── GeminiAdapter ─────────────────────────────────────────────────────────────

_GEMINI_DEFAULT_MODEL   = "gemini-2.0-flash"
_GEMINI_API_BASE        = "https://generativelanguage.googleapis.com/v1beta/models"
_GEMINI_DEFAULT_TIMEOUT = 120


class GeminiAdapter:
    def __init__(self) -> None:
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.model   = os.environ.get("LLM_MODEL", _GEMINI_DEFAULT_MODEL)
        if not self.api_key:
            raise EnvironmentError("GEMINI_API_KEY env var is required when LLM_PROVIDER=gemini")

    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str:
        timeout   = int(os.environ.get("LLM_TIMEOUT_SECONDS", _GEMINI_DEFAULT_TIMEOUT))
        retry_max = int(os.environ.get("LLM_RETRY_MAX", _DEFAULT_RETRY))
        url       = f"{_GEMINI_API_BASE}/{self.model}:generateContent?key={self.api_key}"

        @retry(
            retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            stop=stop_after_attempt(retry_max),
            reraise=True,
        )
        def _call() -> str:
            body = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature":     temperature,
                    "maxOutputTokens": max_tokens,
                    # thinkingConfig must be INSIDE generationConfig (BUG 9 FIX)
                    "thinkingConfig": {"thinkingBudget": 0},
                },
            }
            response = requests.post(
                url,
                headers={"Content-Type": "application/json"},
                json=body,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()

            # BUG 11 FIX: Gemini 2.5+ returns thinking tokens as a separate part
            # with {"thought": True} BEFORE the actual answer part.
            # The old code took parts[0]["text"] unconditionally, which is the raw
            # internal monologue — full of partial JSON and unbalanced braces —
            # causing parse_llm_response to crash with "Unbalanced braces".
            # Fix: skip all thought parts, take the first real text part.
            try:
                parts = data["candidates"][0]["content"]["parts"]
                text = None
                for part in parts:
                    if not part.get("thought", False):
                        text = part.get("text", "")
                        break
                if text is None:
                    raise ValueError("No non-thought part found in Gemini response.")
            except (KeyError, IndexError) as exc:
                raise ValueError(f"Unexpected Gemini response structure: {data}") from exc

            logger.debug("GeminiAdapter response preview: %s", text[:300])
            return text

        return _call()


# ── OpenAIAdapter stub ────────────────────────────────────────────────────────

class OpenAIAdapter:
    def generate(self, prompt: str, temperature: float, max_tokens: int) -> str:
        raise NotImplementedError(
            "OpenAIAdapter is a stub. Implement it or use LLM_PROVIDER=mock|claude|gemini."
        )