"""
ai_pipeline/llm/prompt_builder.py

Builds the strict, machine-parsable prompt that is sent to the LLM.
The template requests JSON-ONLY output so downstream parsing is reliable.
"""

from __future__ import annotations

import json

# ─────────────────────────────────────────────────────────────────────────────
# Template
# ─────────────────────────────────────────────────────────────────────────────

LLM_PROMPT_TEMPLATE: str = """\
You are a personal finance advisor AI. Analyse the financial data below and \
return actionable savings suggestions.

RULES (read carefully):
1. ONLY return valid JSON — no explanation, no markdown, no preamble, no trailing text.
2. The JSON must have exactly one top-level key: "suggestions" (array).
3. Each suggestion object must contain EXACTLY these keys (no others):
   - "action"                        (string, ≤ 255 chars)
   - "explanation"                   (string)
   - "estimated_monthly_saving_in_inr" (number or null)
   - "confidence"                    (one of: "high", "medium", "low")
   - "next_step"                     (string)
   - "tags"                          (array of strings)
4. Do NOT include PII, account numbers, or personal identifiers anywhere.
5. Provide 2–5 suggestions.

FINANCIAL DATA (JSON):
{payload_json}

RESPOND WITH VALID JSON ONLY. NO OTHER TEXT."""


# ─────────────────────────────────────────────────────────────────────────────
# Builder
# ─────────────────────────────────────────────────────────────────────────────

def build_prompt(payload: dict) -> str:
    """
    Embed the pipeline payload into the prompt template.

    Uses compact JSON separators to minimise token usage.

    Args:
        payload: The dict returned by prepare_user_payload().

    Returns:
        A fully formatted prompt string ready to send to the LLM.
    """
    # Compact JSON: fewer tokens, no PII added (sanitizer ran upstream)
    payload_json = json.dumps(payload, separators=(",", ":"), default=str)
    return LLM_PROMPT_TEMPLATE.format(payload_json=payload_json)