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
        return GeminiAdapter()
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


def _make_payload_hash(payload: dict) -> str:
    """
    BUG 10 FIX: Include the active LLM provider and model in the hash so that
    changing LLM_PROVIDER invalidates the dedup cache and forces a fresh LLM call.

    Previously only the transaction payload was hashed. This meant that:
      1. Run with LLM_PROVIDER=mock  → mock insights saved, hash cached 6 hours.
      2. Switch to LLM_PROVIDER=gemini → same payload → same hash → cache hit →
         "skipped" → old mock rows served forever by the view.
    """
    provider = os.environ.get("LLM_PROVIDER", "mock").lower().strip()
    model    = os.environ.get("LLM_MODEL", "").strip()
    hash_input = {
        "payload":  payload,
        "provider": provider,  # BUG 10 FIX: was omitted
        "model":    model,     # BUG 10 FIX: was omitted
    }
    return hashlib.md5(
        json.dumps(hash_input, sort_keys=True, default=str).encode()
    ).hexdigest()


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

    # Skip LLM if data AND provider/model haven't changed (BUG 10 FIX)
    payload_hash   = _make_payload_hash(payload)
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