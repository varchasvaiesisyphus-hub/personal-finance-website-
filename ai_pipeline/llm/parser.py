"""
ai_pipeline/llm/parser.py
BUG 8 FIX: Strip markdown fences before parsing (Gemini sometimes wraps in ```json).
"""
from __future__ import annotations
import json, logging, re
import jsonschema

logger = logging.getLogger(__name__)

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
                "required": ["action", "explanation", "estimated_monthly_saving_in_inr", "confidence", "next_step", "tags"],
                "additionalProperties": False,
                "properties": {
                    "action":                          {"type": "string"},
                    "explanation":                     {"type": "string"},
                    "estimated_monthly_saving_in_inr": {"oneOf": [{"type": "number"}, {"type": "null"}]},
                    "confidence":                      {"type": "string", "enum": ["high", "medium", "low"]},
                    "next_step":                       {"type": "string"},
                    "tags":                            {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}


def _strip_markdown(text: str) -> str:
    """BUG 8 FIX: Remove ```json ... ``` or ``` ... ``` fences Gemini sometimes adds."""
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*",     "", text)
    return text.strip()


def _extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        raise ValueError("No '{' found in LLM response.")
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
                return text[start: i + 1]
    raise ValueError("Unbalanced braces in LLM response.")


def parse_llm_response(text: str) -> dict:
    logger.debug("LLM response preview: %s", text[:300])

    # BUG 8 FIX: strip markdown before any JSON parsing attempt
    text = _strip_markdown(text)

    parsed: dict | None = None

    # Step 1: direct parse
    try:
        parsed = json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Step 2: extract balanced JSON object
    if parsed is None:
        try:
            candidate = _extract_first_json_object(text)
            parsed = json.loads(candidate)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Could not parse JSON from LLM response. Preview: {text[:300]!r}"
            ) from exc

    # Step 3: schema validation
    try:
        jsonschema.validate(instance=parsed, schema=RESPONSE_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise ValueError(
            f"LLM response failed schema validation: {exc.message}. Path: {list(exc.absolute_path)}"
        ) from exc

    return parsed