from __future__ import annotations
import json

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
6. Do NOT repeat any suggestion the user has already rejected.
7. Prioritise suggestions similar to ones the user has accepted.

FINANCIAL DATA (JSON):
{payload_json}

PREVIOUS USER FEEDBACK (act on this):
{feedback_text}

RESPOND WITH VALID JSON ONLY. NO OTHER TEXT."""


def trim_payload(payload: dict) -> dict:
    """Remove fields Claude doesn't need."""
    m = payload.get("metrics", {})
    return {
        "metrics": {
            "total_income":        m.get("total_income"),
            "total_expense":       m.get("total_expense"),
            "avg_monthly_expense": m.get("avg_monthly_expense"),
            "category_breakdown":  m.get("category_breakdown"),
            # drop "trend" — too verbose, Claude rarely uses it
        },
        "recurring":  payload.get("recurring", [])[:5],   # cap at 5
        "anomalies":  payload.get("anomalies", [])[:3],   # cap at 3
        "representative_transactions": [
            {"date": t["date"], "amount": t["amount"], "category": t["category"]}
            for t in payload.get("representative_transactions", [])[:5]
            # drop merchant and sanitized_description — usually empty anyway
        ],
    }


def build_prompt(payload: dict, previous_feedback: list[dict] | None = None) -> str:
    trimmed = trim_payload(payload)
    payload_json = json.dumps(trimmed, separators=(",", ":"), default=str)

    if previous_feedback:
        lines = [
            f'- "{f["action"]}" → {f["feedback"]}ed'
            for f in previous_feedback
        ]
        feedback_text = "\n".join(lines)
    else:
        feedback_text = "None yet."

    return LLM_PROMPT_TEMPLATE.format(
        payload_json=payload_json,
        feedback_text=feedback_text,
    )