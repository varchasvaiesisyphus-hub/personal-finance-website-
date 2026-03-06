"""
ai_pipeline/tasks.py

Celery task wrappers for the ai_pipeline app.

Usage (async):
    from ai_pipeline.tasks import run_generate_insights
    run_generate_insights.delay(user_id=1)

Usage (sync, no broker):
    run_generate_insights(user_id=1)
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="ai_pipeline.run_generate_insights")
def run_generate_insights(self, user_id: int) -> dict:
    """
    Celery task: generate and persist LLM insights for a user.

    Args:
        user_id: Django auth User pk.

    Returns:
        Result dict from generate_insights_for_user, e.g.
        {"status": "ok", "saved": [1, 2, 3]} or {"status": "disabled"}.
    """
    from ai_pipeline.insights import generate_insights_for_user  # noqa: PLC0415

    try:
        result = generate_insights_for_user(user_id)
        logger.info("run_generate_insights completed for user %s: %s", user_id, result)
        return result
    except Exception as exc:
        logger.exception(
            "run_generate_insights failed for user %s: %s", user_id, exc
        )
        raise


@shared_task(bind=True, name="ai_pipeline.run_garvis_for_user")
def run_garvis_for_user(self, user_id: int, days: int = 90) -> dict:
    """
    Celery task: run the non-LLM pipeline (Milestone 2) for a user.

    Args:
        user_id: Django auth User pk.
        days: Lookback window in days.

    Returns:
        The payload dict from prepare_user_payload.
    """
    from django.contrib.auth.models import User  # noqa: PLC0415

    from ai_pipeline.services.orchestrator import prepare_user_payload  # noqa: PLC0415

    try:
        user = User.objects.get(pk=user_id)
        payload = prepare_user_payload(user, days=days)
        logger.info("run_garvis_for_user completed for user %s", user_id)
        return payload
    except Exception as exc:
        logger.exception("run_garvis_for_user failed for user %s: %s", user_id, exc)
        raise