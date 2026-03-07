"""
ai_pipeline/insights.py
BUG 1 FIX: GeminiAdapter added to get_adapter() import and routing.
BUG 2 FIX: LLM_MAX_TOKENS default changed from 400 to 8000.
"""
from __future__ import annotations
import hashlib, json, logging, os
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger(__name__)


def get_adapter():
    # BUG 1 FIX: GeminiAdapter is now imported and routed
    from ai_pipeline.llm.llm_adapter import ClaudeAdapter, GeminiAdapter, MockAdapter, OpenAIAdapter
    provider = os.environ.get("LLM_PROVIDER", "mock").lower().strip()
    if provider == "claude":
        return ClaudeAdapter()
    if provider == "gemini":
        return GeminiAdapter()   # BUG 1 FIX
    if provider == "openai":
        return OpenAIAdapter()
    return MockAdapter()


_MAX_ACTION_LEN      = 255
_MAX_EXPLANATION_LEN = 2000
_MAX_NEXT_STEP_LEN   = 500


def _sanitise_suggestion(raw: dict) -> dict:
    return {
        "action":                   raw["action"][:_MAX_ACTION_LEN],
        "explanation":              raw["explanation"][:_MAX_EXPLANATION_LEN],
        "estimated_monthly_saving": raw.get("estimated_monthly_saving_in_inr"),
        "confidence":               raw["confidence"],
        "next_step":                raw["next_step"][:_MAX_NEXT_STEP_LEN],
        "tags":                     raw.get("tags", []),
    }


def generate_insights_for_user(user_id: int) -> dict:
    from ai_pipeline.models import AIInsight

    user = User.objects.get(pk=user_id)

    # Respect AIPreferences
    try:
        from ai_pipeline.models import AIPreferences
        prefs = AIPreferences.objects.get(user=user)
        if not prefs.ai_enabled:
            logger.info("AI disabled for user %s — skipping.", user_id)
            return {"status": "disabled"}
    except Exception:
        pass

    # Build pipeline payload
    days = int(os.environ.get("AI_PIPELINE_DAYS", 90))
    from ai_pipeline.services.orchestrator import prepare_user_payload
    payload = prepare_user_payload(user, days=days)

    # Skip LLM if data hasn't changed
    payload_hash   = hashlib.md5(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    hash_cache_key = f"garvis_hash_{user_id}"
    if cache.get(hash_cache_key) == payload_hash:
        logger.info("Payload unchanged for user %s — skipping LLM call.", user_id)
        return {"status": "skipped", "reason": "data unchanged"}

    # Build prompt with feedback history
    from ai_pipeline.llm.prompt_builder import build_prompt
    previous_feedback = list(
        AIInsight.objects
        .filter(user=user, feedback__isnull=False)
        .values("action", "feedback")
        .order_by("-created_at")[:5]
    )
    prompt = build_prompt(payload, previous_feedback=previous_feedback)
    logger.debug("Prompt preview: %s", prompt[:500])

    # LLM call
    adapter     = get_adapter()
    temperature = float(os.environ.get("LLM_TEMPERATURE", 0.2))
    max_tokens  = int(os.environ.get("LLM_MAX_TOKENS", 8000))  # BUG 2 FIX: was 400
    raw_response = adapter.generate(prompt, temperature=temperature, max_tokens=max_tokens)
    logger.debug("LLM response preview: %s", raw_response[:500])

    # Parse & validate
    from ai_pipeline.llm.parser import parse_llm_response
    parsed      = parse_llm_response(raw_response)
    suggestions = parsed["suggestions"]

    # Persist
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
        logger.exception("DB error persisting insights for user %s", user_id)
        raise

    cache.set(hash_cache_key, payload_hash, 60 * 60 * 6)
    logger.info("Saved %d insights for user %s: ids=%s", len(saved_ids), user_id, saved_ids)
    return {"status": "ok", "saved": saved_ids}