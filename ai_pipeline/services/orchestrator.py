"""
ai_pipeline/services/orchestrator.py
BUG 4 FIX: adds _build_reason_breakdown() and includes reason_breakdown in payload.
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
from .metrics import compute_metrics
from .recurring import detect_recurring
from .representative import select_representative
from .sanitizer import sanitize_transactions

logger = logging.getLogger(__name__)


def _is_transfer(tx: Transaction) -> bool:
    """Return True if this transaction is an internal transfer (not a real expense)."""
    cat = getattr(tx, "category", None)
    cat_name = str(getattr(cat, "name", cat) if cat else "").lower()
    return cat_name == "transfer"


def _build_reason_breakdown(transactions: List[Transaction]) -> Dict[str, List[str]]:
    """
    BUG 4 FIX: Map category name -> sorted list of distinct user-entered reasons.
    Expense-only, transfers excluded, capped at 10 per category.
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

    # Guard: check ai_enabled
    try:
        from ai_pipeline.models import AIPreferences
        prefs = AIPreferences.objects.filter(user=user).first()
        if prefs is not None and not prefs.ai_enabled:
            logger.info("AI pipeline disabled for user=%s", user.pk)
            return _disabled_payload(user, days, computed_at)
    except Exception as exc:
        logger.warning("Could not check AIPreferences for user=%s: %s", user.pk, exc)

    end_date: date   = computed_at.date()
    start_date: date = end_date - timedelta(days=days)
    logger.info("prepare_user_payload: user=%s window=%s -> %s", user.pk, start_date, end_date)

    # Fetch transactions
    try:
        transactions = list(
            Transaction.objects.filter(user=user, date__gte=start_date, date__lte=end_date)
            .select_related("category").order_by("date", "pk")
        )
    except Exception as exc:
        logger.error("Failed to fetch transactions: %s", exc)
        transactions = []

    logger.info("Fetched %d transactions", len(transactions))

    # Metrics
    try:
        metrics = compute_metrics(user, transactions, start_date, end_date)
    except Exception as exc:
        logger.error("Metrics failed: %s", exc)
        metrics = {"total_income": 0.0, "total_expense": 0.0, "avg_monthly_expense": 0.0, "category_breakdown": {}, "trend": {}}

    # Reason breakdown (BUG 4 FIX)
    try:
        reason_breakdown = _build_reason_breakdown(transactions)
    except Exception as exc:
        logger.error("Reason breakdown failed: %s", exc)
        reason_breakdown = {}

    # Recurring
    try:
        recurring = detect_recurring(transactions)
    except Exception as exc:
        logger.error("Recurring detection failed: %s", exc)
        recurring = []

    # Anomalies
    try:
        anomalies = detect_anomalies(transactions)
    except Exception as exc:
        logger.error("Anomaly detection failed: %s", exc)
        anomalies = []

    # Sanitiser
    try:
        sanitised, sanitization_log = sanitize_transactions(transactions)
    except Exception as exc:
        logger.error("Sanitisation failed: %s", exc)
        sanitised, sanitization_log = [], {"redacted_fields_count": 0, "redaction_examples": []}

    # Representative
    try:
        representative_transactions = select_representative(sanitised, recurring, anomalies)
    except Exception as exc:
        logger.error("Representative selection failed: %s", exc)
        representative_transactions = []

    payload: Dict[str, Any] = {
        "user_id":                     user.pk,
        "start_date":                  str(start_date),
        "end_date":                    str(end_date),
        "metrics":                     metrics,
        "reason_breakdown":            reason_breakdown,   # BUG 4 FIX
        "recurring":                   recurring,
        "anomalies":                   anomalies,
        "representative_transactions": representative_transactions,
        "sanitization_log":            sanitization_log,
        "meta": {"days": days, "computed_at": computed_at.isoformat()},
    }
    logger.info("Payload assembled for user=%s", user.pk)
    return payload


def _disabled_payload(user: User, days: int, computed_at: Any) -> Dict[str, Any]:
    end_date   = computed_at.date()
    start_date = end_date - timedelta(days=days)
    return {
        "user_id":    user.pk,
        "start_date": str(start_date),
        "end_date":   str(end_date),
        "metrics": {"total_income": 0.0, "total_expense": 0.0, "avg_monthly_expense": 0.0, "category_breakdown": {}, "trend": {}},
        "reason_breakdown":            {},
        "recurring":                   [],
        "anomalies":                   [],
        "representative_transactions": [],
        "sanitization_log": {"redacted_fields_count": 0, "redaction_examples": []},
        "meta": {"days": days, "computed_at": computed_at.isoformat(), "ai_enabled": False},
    }