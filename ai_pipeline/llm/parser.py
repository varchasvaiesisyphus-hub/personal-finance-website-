"""
ai_pipeline/llm/parser.py

Parses and validates the raw text returned by the LLM.

Strategy:
1. Preliminary cleanup: remove common Markdown wrappers (```json ... ```).
2. Scan for the first balanced '{...}' substring using a brace-tracking loop.
   This handles models that prepend/append stray text despite instructions.
3. Validate the parsed object against RESPONSE_SCHEMA using jsonschema.
4. Raise ValueError with a clear message on any failure.
"""

from __future__ import annotations

import json
import logging
import re
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
    Finds and returns the first balanced JSON-like '{...}' string.
    
    Logic:
    - Removes markdown triple-backticks.
    - Walks character-by-character to find the first '{' and its matching '}'.
    - Ignores braces inside strings (double quotes) and respects backslash escapes.
    """
    # 1. Strip Markdown noise
    text = re.sub(r"```json\s*|\s*```", "", text).strip()

    start = text.find("{")
    if start == -1:
        raise ValueError("No '{' found in LLM response.")

    depth = 0
    in_string = False
    escape_next = False

    # 2. Brace tracking loop
    for i, ch in enumerate(text[start:], start=start):
        if escape_next:
            escape_next = False
            continue
        
        if ch == "\\":
            # Only escape next if we are currently inside a string
            if in_string:
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

    raise ValueError("Unbalanced braces in LLM response — could not extract a complete JSON object.")


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def parse_llm_response(text: str) -> dict:
    """
    Parse and validate the raw LLM response text.

    Args:
        text: Raw string returned by the adapter's generate() method.

    Returns:
        Validated dict with key "suggestions".

    Raises:
        ValueError: If parsing or schema validation fails.
    """
    logger.debug("Parsing LLM response (first 100 chars): %s", text[:100])

    # Attempt extraction and parsing
    try:
        json_str = _extract_first_json_object(text)
        parsed = json.loads(json_str)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("JSON extraction failed. Raw text snippet: %r", text[:300])
        raise ValueError(
            f"Failed to extract/parse JSON from LLM response: {exc}. "
            f"Response preview: {text[:200]!r}"
        ) from exc

    # Schema validation
    try:
        jsonschema.validate(instance=parsed, schema=RESPONSE_SCHEMA)
    except jsonschema.ValidationError as exc:
        logger.error("Schema validation failed: %s", exc.message)
        raise ValueError(
            f"LLM response failed schema validation: {exc.message}. "
            f"Path: {list(exc.absolute_path)}"
        ) from exc

    return parsed