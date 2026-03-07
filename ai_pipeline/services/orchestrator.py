"""
ai_pipeline/services/orchestrator.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Single public function ``prepare_user_payload``.

New: builds ``reason_breakdown`` — a per-category list of distinct user-entered
reasons — so the LLM can name specific services and habits in its suggestions.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List

from django.contrib.auth.models import User
from django.utils import timezone

from core.models import Transaction

from .anomaly import detect_anomalies
from .metrics import compute_metrics, _is_transfer
from .recurring import detect_recurring
from .representative import select_representative
from .sanitizer import sanitize_transactions

logger = logging.getLogger(__name__)


def _build_reason_breakdown(transactions: List[Transaction]) -> Dict[str, List[str]]:
    """
    Map category → sorted list of distinct non-empty reasons (expense only,
    transfers excluded). Capped at 10 reasons per category for token efficiency.
    """
    cat_reasons: Dict[str, set] = defaultdict(set)
    for tx in transactions:
        if getattr(tx, "type", "expense") != "expense":
            continue
        if _is_transfer(tx):
            continue
        reason = (getattr(tx, "reason", "") or "").strip()
        if not reason:
            continue
        cat = str(getattr(getattr(tx, "category", None), "name", "Unknown"))
        cat_reasons[cat].add(reason)

    return {
        cat: sorted(reasons)[:10]
        for cat, reasons in cat_reasons.items()
        if reasons
    }


def prepare_user_payload(user: User, days: int = 90) -> Dict[str, Any]:
    computed_at = timezone.now()

    try:
        from ai_pipeline.models import AIPreferences
        prefs = AIPreferences.objects.filter(user=user).first()
        if prefs is not None and not prefs.ai_enabled:
            logger.info("AI pipeline disabled for user=%s — skipping.", user.pk)
            return _disabled_payload(user, days, computed_at)
    except Exception as exc:
        logger.warning("Could not check AIPreferences for user=%s: %s", user.pk, exc)

    end_date: date   = computed_at.date()
    start_date: date = end_date - timedelta(days=days)

    logger.info("prepare_user_payload: user=%s window=%s → %s (%d days)",
                user.pk, start_date, end_date, days)

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

    try:
        metrics = compute_metrics(user, transactions, start_date, end_date)
    except Exception as exc:
        logger.error("Metrics failed: %s", exc)
        metrics = {
            "total_income": 0.0, "total_expense": 0.0,
            "avg_monthly_expense": 0.0, "category_breakdown": {}, "trend": {},
        }

    try:
        reason_breakdown = _build_reason_breakdown(transactions)
    except Exception as exc:
        logger.error("Reason breakdown failed: %s", exc)
        reason_breakdown = {}

    try:
        recurring = detect_recurring(transactions)
    except Exception as exc:
        logger.error("Recurring detection failed for user=%s: %s", user.pk, exc)
        recurring = []

    try:
        anomalies = detect_anomalies(transactions)
    except Exception as exc:
        logger.error("Anomaly detection failed for user=%s: %s", user.pk, exc)
        anomalies = []

    try:
        sanitised, sanitization_log = sanitize_transactions(transactions)
    except Exception as exc:
        logger.error("Sanitisation failed for user=%s: %s", user.pk, exc)
        sanitised, sanitization_log = [], {"redacted_fields_count": 0, "redaction_examples": []}

    try:
        representative_transactions = select_representative(sanitised, recurring, anomalies)
    except Exception as exc:
        logger.error("Representative selection failed for user=%s: %s", user.pk, exc)
        representative_transactions = []

    payload: Dict[str, Any] = {
        "user_id":                     user.pk,
        "start_date":                  str(start_date),
        "end_date":                    str(end_date),
        "metrics":                     metrics,
        "reason_breakdown":            reason_breakdown,   # ← NEW
        "recurring":                   recurring,
        "anomalies":                   anomalies,
        "representative_transactions": representative_transactions,
        "sanitization_log":            sanitization_log,
        "meta": {
            "days":        days,
            "computed_at": computed_at.isoformat(),
        },
    }

    logger.info("Payload assembled for user=%s", user.pk)
    return payload


def _disabled_payload(user: User, days: int, computed_at: Any) -> Dict[str, Any]:
    end_date   = computed_at.date()
    start_date = end_date - timedelta(days=days)
    return {
        "user_id":          user.pk,
        "start_date":       str(start_date),
        "end_date":         str(end_date),
        "metrics": {
            "total_income": 0.0, "total_expense": 0.0,
            "avg_monthly_expense": 0.0, "category_breakdown": {}, "trend": {},
        },
        "reason_breakdown":            {},
        "recurring":                   [],
        "anomalies":                   [],
        "representative_transactions": [],
        "sanitization_log":            {"redacted_fields_count": 0, "redaction_examples": []},
        "meta": {
            "days": days,
            "computed_at": computed_at.isoformat(),
            "ai_enabled": False,
        },
    }