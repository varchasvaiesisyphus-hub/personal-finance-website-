"""
ai_pipeline/views.py

Plain Django views for the Garvis AI insights API.
No DRF required — uses login_required + JsonResponse.
Caching: 30-second per-user cache on the latest insights list.
"""
from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import AIInsight

logger = logging.getLogger(__name__)

_CACHE_TTL = 30  # seconds


def _insight_to_dict(insight: AIInsight) -> dict:
    return {
        "id": insight.pk,
        "action": insight.action,
        "explanation": insight.explanation,
        "estimated_monthly_saving": insight.estimated_monthly_saving,
        "confidence": insight.confidence,
        "next_step": insight.next_step,
        "tags": insight.tags or [],
        "feedback": insight.feedback,
    }


@login_required
def api_latest_insights(request):
    """
    GET /api/ai/insights/latest/
    Returns the latest 3 AIInsight rows for the logged-in user.
    Results are cached per-user for 30 seconds.
    """
    cache_key = f"garvis_insights_{request.user.pk}"
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({"insights": cached})

    insights = (
        AIInsight.objects
        .filter(user=request.user)
        .exclude(action="draft_pipeline_output")  # skip Milestone 2 drafts
        .order_by("-created_at")[:3]
    )
    data = [_insight_to_dict(i) for i in insights]
    cache.set(cache_key, data, _CACHE_TTL)
    return JsonResponse({"insights": data})


@login_required
@require_http_methods(["POST"])
def api_insight_feedback(request, pk: int):
    """
    POST /api/ai/insights/<pk>/feedback/
    Body: {"feedback": "accept" | "reject"}
    Updates the insight's feedback field. User must own the insight.
    """
    try:
        insight = AIInsight.objects.get(pk=pk, user=request.user)
    except AIInsight.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    feedback = body.get("feedback", "").strip().lower()
    if feedback not in ("accept", "reject"):
        return JsonResponse(
            {"error": "feedback must be 'accept' or 'reject'"}, status=400
        )

    insight.feedback = feedback
    insight.save(update_fields=["feedback"])

    # Bust the cache so the next fetch reflects the update
    cache_key = f"garvis_insights_{request.user.pk}"
    cache.delete(cache_key)

    logger.info("User %s set feedback=%s on insight %s", request.user.pk, feedback, pk)
    return JsonResponse({"status": "ok", "id": pk, "feedback": feedback})