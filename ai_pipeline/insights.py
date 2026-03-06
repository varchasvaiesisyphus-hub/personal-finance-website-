"""
ai_pipeline/insights.py

Public entry point for Milestone 3: LLM Orchestration.

generate_insights_for_user(user_id) orchestrates the full pipeline:
  pipeline payload → prompt → LLM → parse → validate → persist → return ids
"""

from __future__ import annotations

import logging
import os

from django.contrib.auth.models import User
from django.db import transaction

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Lazy imports (defensive — works regardless of package layout)
# ─────────────────────────────────────────────────────────────────────────────

def _get_prepare_user_payload():
    """Import prepare_user_payload defensively."""
    from ai_pipeline.services.orchestrator import prepare_user_payload  # noqa: PLC0415
    return prepare_user_payload


def _get_ai_insight_model():
    from ai_pipeline.models import AIInsight  # noqa: PLC0415
    return AIInsight


def _get_ai_preferences_model():
    try:
        from ai_pipeline.models import AIPreferences  # noqa: PLC0415
        return AIPreferences
    except ImportError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Adapter factory
# ─────────────────────────────────────────────────────────────────────────────

def get_adapter():
    """
    Return the appropriate LLM adapter based on the LLM_PROVIDER env var.

    Supported values: mock (default) | claude | openai
    """
    from ai_pipeline.llm.llm_adapter import ClaudeAdapter, MockAdapter, OpenAIAdapter  # noqa: PLC0415

    provider = os.environ.get("LLM_PROVIDER", "mock").lower().strip()
    if provider == "claude":
        return ClaudeAdapter()
    if provider == "openai":
        return OpenAIAdapter()
    # Default: mock (safe for tests and CI)
    return MockAdapter()


# ─────────────────────────────────────────────────────────────────────────────
# Suggestion sanitiser
# ─────────────────────────────────────────────────────────────────────────────

_MAX_ACTION_LEN = 255
_MAX_EXPLANATION_LEN = 2000
_MAX_NEXT_STEP_LEN = 500


def _sanitise_suggestion(raw: dict) -> dict:
    """
    Trim overly long string fields and enforce hard DB limits.
    Returns a new dict safe to write to AIInsight.
    """
    return {
        "action": raw["action"][:_MAX_ACTION_LEN],
        "explanation": raw["explanation"][:_MAX_EXPLANATION_LEN],
        "estimated_monthly_saving": raw.get("estimated_monthly_saving_in_inr"),
        "confidence": raw["confidence"],
        "next_step": raw["next_step"][:_MAX_NEXT_STEP_LEN],
        "tags": raw.get("tags", []),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public function
# ─────────────────────────────────────────────────────────────────────────────

def generate_insights_for_user(user_id: int) -> dict:
    """
    Full Milestone 3 pipeline for a single user.

    Steps:
      1. Load user & check AIPreferences.ai_enabled.
      2. Build the pipeline payload (prepare_user_payload).
      3. Build the LLM prompt (build_prompt).
      4. Call the configured LLM adapter.
      5. Parse and validate the response (parse_llm_response).
      6. Persist each suggestion as an AIInsight row (atomic).
      7. Return {"status": "ok", "saved": [<ids>]}.

    Args:
        user_id: Django auth User pk.

    Returns:
        {"status": "ok", "saved": [int, ...]}
        or {"status": "disabled"} if ai_enabled is False.

    Raises:
        User.DoesNotExist: If user_id is invalid.
        ValueError: If LLM response fails parsing/validation.
        Exception: DB errors are logged then re-raised.
    """
    # ── 1. Load user ──
    user = User.objects.get(pk=user_id)

    # ── 1b. Respect AIPreferences ──
    AIPreferences = _get_ai_preferences_model()
    if AIPreferences is not None:
        try:
            prefs = AIPreferences.objects.get(user=user)
            if not prefs.ai_enabled:
                logger.info("AI disabled for user %s — skipping insight generation.", user_id)
                return {"status": "disabled"}
        except AIPreferences.DoesNotExist:
            pass  # No prefs row → treat as enabled

    # ── 2. Pipeline payload ──
    days = int(os.environ.get("AI_PIPELINE_DAYS", 90))
    prepare_user_payload = _get_prepare_user_payload()
    payload = prepare_user_payload(user, days=days)

    # ── 3. Prompt ──
    from ai_pipeline.llm.prompt_builder import build_prompt  # noqa: PLC0415
    prompt = build_prompt(payload)
    logger.debug("Prompt preview: %s", prompt[:300])

    # ── 4. LLM call ──
    adapter = get_adapter()
    temperature = float(os.environ.get("LLM_TEMPERATURE", 0.2))
    max_tokens = int(os.environ.get("LLM_MAX_TOKENS", 800))
    raw_response = adapter.generate(prompt, temperature=temperature, max_tokens=max_tokens)
    logger.debug("LLM response preview: %s", raw_response[:300])

    # ── 5. Parse & validate ──
    from ai_pipeline.llm.parser import parse_llm_response  # noqa: PLC0415
    parsed = parse_llm_response(raw_response)
    suggestions = parsed["suggestions"]

    # ── 6. Persist ──
    AIInsight = _get_ai_insight_model()
    saved_ids: list[int] = []

    try:
        with transaction.atomic():
            for raw_suggestion in suggestions:
                clean = _sanitise_suggestion(raw_suggestion)
                insight = AIInsight.objects.create(
                    user=user,
                    action=clean["action"],
                    explanation=clean["explanation"],
                    estimated_monthly_saving=clean["estimated_monthly_saving"],
                    confidence=clean["confidence"],
                    next_step=clean["next_step"],
                    tags=clean["tags"],
                )
                saved_ids.append(insight.pk)
    except Exception:
        logger.exception(
            "DB error while persisting insights for user %s — rolling back.", user_id
        )
        raise

    logger.info("Saved %d insights for user %s: ids=%s", len(saved_ids), user_id, saved_ids)
    return {"status": "ok", "saved": saved_ids}