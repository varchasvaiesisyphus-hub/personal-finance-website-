"""
ai_pipeline/llm/parser.py

Parses and validates the raw text returned by the LLM.

Strategy:
1. Try json.loads(text) directly — works when the model is well-behaved.
2. If that fails, scan for the first balanced '{...}' substring and retry.
   This handles models that prepend/append stray text despite instructions.
3. Validate the parsed object against RESPONSE_SCHEMA using jsonschema.
4. Raise ValueError with a clear message on any failure.
"""

from __future__ import annotations

import json
import logging

import jsonschema

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Validation schema
# ─────────────────────────────────────────────────────────────────────────────

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "required": ["suggestions"],
    "additionalProperties": False,
    "properties": {
        "suggestions": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "action",
                    "explanation",
                    "estimated_monthly_saving_in_inr",
                    "confidence",
                    "next_step",
                    "tags",
                ],
                "additionalProperties": False,
                "properties": {
                    "action": {"type": "string"},
                    "explanation": {"type": "string"},
                    "estimated_monthly_saving_in_inr": {
                        "oneOf": [{"type": "number"}, {"type": "null"}]
                    },
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "next_step": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        }
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_first_json_object(text: str) -> str:
    """
    Extract the first balanced '{...}' substring from *text*.

    Walks character-by-character tracking brace depth.
    Returns the substring (including braces) or raises ValueError if none found.
    """
    start = text.find("{")
    if start == -1:
        raise ValueError("No '{' found in LLM response — cannot extract JSON object.")

    depth = 0
    in_string = False
    escape_next = False

    for i, ch in enumerate(text[start:], start=start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    raise ValueError("Unbalanced braces in LLM response — could not extract JSON object.")


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def parse_llm_response(text: str) -> dict:
    """
    Parse and validate the raw LLM response text.

    Args:
        text: Raw string returned by the adapter's generate() method.

    Returns:
        Validated dict with key "suggestions" (list of suggestion dicts).

    Raises:
        ValueError: If the text cannot be parsed as JSON or fails schema validation.
    """
    logger.debug("LLM response preview: %s", text[:300])

    # Step 1 — optimistic direct parse
    parsed: dict | None = None
    try:
        parsed = json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Step 2 — fallback: extract first balanced JSON object
    if parsed is None:
        try:
            candidate = _extract_first_json_object(text)
            parsed = json.loads(candidate)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Could not parse a JSON object from LLM response. "
                f"Response preview: {text[:300]!r}"
            ) from exc

    # Step 3 — schema validation
    try:
        jsonschema.validate(instance=parsed, schema=RESPONSE_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise ValueError(
            f"LLM response failed schema validation: {exc.message}. "
            f"Path: {list(exc.absolute_path)}"
        ) from exc

    return parsed