"""
ai_pipeline/tasks.py
~~~~~~~~~~~~~~~~~~~~~~
Celery task skeleton for the Garvis pipeline.

To use Celery, add ``celery`` to your requirements and configure a broker
(e.g. Redis) in settings.  The tasks below work standalone with Django's
``call_command`` or through a Celery worker.

Example (without Celery broker — direct call):
    from ai_pipeline.tasks import run_garvis_for_user
    run_garvis_for_user(user_id=1)

Example (with Celery):
    run_garvis_for_user.delay(user_id=1)
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Attempt to import Celery.  If it is not installed the module still loads and
# the task can be called synchronously.
# ---------------------------------------------------------------------------
try:
    from celery import shared_task
    _celery_available = True
except ImportError:
    _celery_available = False

    # Provide a no-op decorator so the code below works without Celery.
    def shared_task(func=None, **kwargs):  # type: ignore[misc]
        if func is not None:
            return func
        def decorator(f):
            return f
        return decorator


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_garvis_for_user(self_or_user_id, user_id: int = 0, days: int = 90) -> Dict[str, Any]:
    """
    Celery task: run the Garvis pipeline for a single user and persist a
    draft AIInsight row.

    Parameters
    ----------
    user_id : int
        Primary key of the Django auth User.
    days : int
        Look-back window in days (default 90).

    Returns
    -------
    dict with keys ``insight_id``, ``user_id``, ``status``.
    """
    # When called via Celery, ``self_or_user_id`` is the bound task instance.
    # When called directly (no Celery), ``self_or_user_id`` receives user_id.
    if isinstance(self_or_user_id, int):
        # Direct call: run_garvis_for_user(user_id)
        user_id = self_or_user_id
        task_self = None
    else:
        task_self = self_or_user_id  # Celery task instance

    logger.info("run_garvis_for_user: user_id=%s days=%s", user_id, days)

    from django.contrib.auth.models import User

    from ai_pipeline.models import AIInsight
    from ai_pipeline.services.orchestrator import prepare_user_payload

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error("User id=%s not found — aborting task.", user_id)
        return {"status": "error", "detail": f"User {user_id} not found"}

    try:
        payload = prepare_user_payload(user, days=days)
    except Exception as exc:
        logger.exception("Pipeline error for user=%s", user_id)
        if task_self and _celery_available:
            raise task_self.retry(exc=exc)
        return {"status": "error", "detail": str(exc)}

    try:
        insight = AIInsight.objects.create(
            user=user,
            action=AIInsight.ACTION_DRAFT,
            payload=payload,
            days=days,
        )
        logger.info("AIInsight created: id=%s for user=%s", insight.pk, user_id)
        return {
            "status": "ok",
            "insight_id": insight.pk,
            "user_id": user_id,
        }
    except Exception as exc:
        logger.exception("Failed to persist AIInsight for user=%s", user_id)
        return {"status": "error", "detail": str(exc)}