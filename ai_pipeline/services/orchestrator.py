"""
ai_pipeline/services/orchestrator.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Single public function ``prepare_user_payload`` that orchestrates all
pipeline steps and returns a JSON-serialisable payload.

Short-circuits (returns a minimal disabled-payload) if the user's
AIPreferences.ai_enabled is False.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict

from django.contrib.auth.models import User
from django.utils import timezone

from core.models import Transaction

from .anomaly import detect_anomalies
from .metrics import compute_metrics
from .recurring import detect_recurring
from .representative import select_representative
from .sanitizer import sanitize_transactions

logger = logging.getLogger(__name__)


def prepare_user_payload(user: User, days: int = 90) -> Dict[str, Any]:
    """
    Run the full non-LLM pipeline for a user and return a structured payload.

    Parameters
    ----------
    user : Django auth User instance.
    days : Look-back window in days (default 90).

    Returns
    -------
    Dict matching the exact orchestrator payload schema.  All numeric values
    are native Python floats (Decimal-free) and the dict is JSON-serialisable.

    Raises
    ------
    Does NOT raise.  Errors in individual services are caught and logged; the
    corresponding section will be an empty list / dict.
    """
    computed_at = timezone.now()

    # ── Guard: check ai_enabled ──────────────────────────────────────────────
    try:
        from ai_pipeline.models import AIPreferences
        prefs = AIPreferences.objects.filter(user=user).first()
        if prefs is not None and not prefs.ai_enabled:
            logger.info("AI pipeline disabled for user=%s — skipping.", user.pk)
            return _disabled_payload(user, days, computed_at)
    except Exception as exc:
        logger.warning("Could not check AIPreferences for user=%s: %s", user.pk, exc)

    # ── Date window ──────────────────────────────────────────────────────────
    end_date: date = computed_at.date()
    start_date: date = end_date - timedelta(days=days)

    logger.info(
        "prepare_user_payload: user=%s window=%s → %s (%d days)",
        user.pk, start_date, end_date, days,
    )

    # ── Fetch transactions ───────────────────────────────────────────────────
    logger.info("Fetching transactions for user=%s", user.pk)
    try:
        transactions = list(
            Transaction.objects.filter(
                user=user,
                date__gte=start_date,
                date__lte=end_date,
            )
            .select_related("category")
            .order_by("date", "pk")
        )
    except Exception as exc:
        logger.error("Failed to fetch transactions for user=%s: %s", user.pk, exc)
        transactions = []

    logger.info("Fetched %d transactions", len(transactions))

    # ── Metrics ──────────────────────────────────────────────────────────────
    logger.info("Step: metrics")
    try:
        metrics = compute_metrics(user, transactions, start_date, end_date)
    except Exception as exc:
        logger.error("Metrics failed for user=%s: %s", user.pk, exc)
        metrics = {
            "total_income": 0.0,
            "total_expense": 0.0,
            "avg_monthly_expense": 0.0,
            "category_breakdown": {},
            "trend": {},
        }

    # ── Recurring ────────────────────────────────────────────────────────────
    logger.info("Step: recurring detection")
    try:
        recurring = detect_recurring(transactions)
    except Exception as exc:
        logger.error("Recurring detection failed for user=%s: %s", user.pk, exc)
        recurring = []

    # ── Anomalies ────────────────────────────────────────────────────────────
    logger.info("Step: anomaly detection")
    try:
        anomalies = detect_anomalies(transactions)
    except Exception as exc:
        logger.error("Anomaly detection failed for user=%s: %s", user.pk, exc)
        anomalies = []

    # ── Sanitiser ────────────────────────────────────────────────────────────
    logger.info("Step: sanitisation")
    try:
        sanitised, sanitization_log = sanitize_transactions(transactions)
    except Exception as exc:
        logger.error("Sanitisation failed for user=%s: %s", user.pk, exc)
        sanitised, sanitization_log = [], {"redacted_fields_count": 0, "redaction_examples": []}

    # ── Representative transactions ──────────────────────────────────────────
    logger.info("Step: representative selection")
    try:
        representative_transactions = select_representative(sanitised, recurring, anomalies)
    except Exception as exc:
        logger.error("Representative selection failed for user=%s: %s", user.pk, exc)
        representative_transactions = []

    # ── Assemble payload ─────────────────────────────────────────────────────
    payload: Dict[str, Any] = {
        "user_id": user.pk,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "metrics": metrics,
        "recurring": recurring,
        "anomalies": anomalies,
        "representative_transactions": representative_transactions,
        "sanitization_log": sanitization_log,
        "meta": {
            "days": days,
            "computed_at": computed_at.isoformat(),
        },
    }

    logger.info("Payload assembled for user=%s", user.pk)
    return payload


# ──────────────────────────────────────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────────────────────────────────────

def _disabled_payload(user: User, days: int, computed_at: Any) -> Dict[str, Any]:
    end_date = computed_at.date()
    start_date = end_date - timedelta(days=days)
    return {
        "user_id": user.pk,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "metrics": {
            "total_income": 0.0,
            "total_expense": 0.0,
            "avg_monthly_expense": 0.0,
            "category_breakdown": {},
            "trend": {},
        },
        "recurring": [],
        "anomalies": [],
        "representative_transactions": [],
        "sanitization_log": {"redacted_fields_count": 0, "redaction_examples": []},
        "meta": {
            "days": days,
            "computed_at": computed_at.isoformat(),
            "ai_enabled": False,
        },
    }