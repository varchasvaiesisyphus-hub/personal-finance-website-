"""
ai_pipeline/services/metrics.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Fetch transactions for a user over a date window and compute aggregates:
  - total income / expense
  - average monthly expense
  - per-category expense breakdown
  - 3-month vs prior-3-month trend per category
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List

from django.contrib.auth.models import User
from django.utils import timezone

from core.models import Transaction

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _tx_amount(tx: Transaction) -> float:
    """Safely convert a transaction's amount to float."""
    return round(float(getattr(tx, "amount", 0) or 0), 2)


def _tx_category(tx: Transaction) -> str:
    """Return a stable string label for the transaction's category."""
    cat = getattr(tx, "category", None)
    if cat is not None:
        return str(getattr(cat, "name", cat))
    return getattr(tx, "category_name", "Unknown")


def _month_key(d: date) -> str:
    """Return 'YYYY-MM' for a date."""
    return f"{d.year:04d}-{d.month:02d}"


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def compute_metrics(
    user: User,
    transactions: List[Transaction],
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    """
    Compute financial aggregates from a pre-fetched list of transactions.

    Parameters
    ----------
    user:         The owning user (used only for logging).
    transactions: All transactions in the look-back window (income + expense).
    start_date:   Inclusive start of the window.
    end_date:     Inclusive end of the window.

    Returns
    -------
    A dict matching the ``metrics`` key of the orchestrator payload schema.
    """
    logger.info("Computing metrics for user=%s (%d transactions)", user.pk, len(transactions))

    total_income: float = 0.0
    total_expense: float = 0.0

    # category → monthly totals  (for breakdown + trend)
    cat_monthly: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for tx in transactions:
        amt = _tx_amount(tx)
        tx_type = getattr(tx, "type", "expense") or "expense"
        tx_date: date = getattr(tx, "date", end_date)
        category = _tx_category(tx)
        month = _month_key(tx_date)

        if tx_type == "income":
            total_income += amt
        else:
            total_expense += amt
            cat_monthly[category][month] += amt

    # ── Average monthly expense ──────────────────────────────────────────────
    # Count distinct months that had *any* expense activity
    all_expense_months: set[str] = set()
    for monthly in cat_monthly.values():
        all_expense_months.update(monthly.keys())

    if all_expense_months:
        avg_monthly_expense = round(total_expense / len(all_expense_months), 2)
    else:
        avg_monthly_expense = 0.0

    # ── Category breakdown (total over the full window) ──────────────────────
    category_breakdown: Dict[str, float] = {
        cat: round(sum(monthly.values()), 2)
        for cat, monthly in cat_monthly.items()
    }

    # ── 3-month trend ────────────────────────────────────────────────────────
    # Determine the midpoint: 3 months back from end_date
    mid_date = _subtract_months(end_date, 3)
    trend: Dict[str, Dict[str, float]] = {}

    for cat, monthly in cat_monthly.items():
        last_3m = sum(v for k, v in monthly.items() if k >= _month_key(mid_date))
        prev_3m = sum(v for k, v in monthly.items() if k < _month_key(mid_date))

        if prev_3m == 0:
            delta_pct = 100.0 if last_3m > 0 else 0.0
        else:
            delta_pct = round((last_3m - prev_3m) / prev_3m * 100, 2)

        trend[cat] = {
            "last_3m": round(last_3m, 2),
            "prev_3m": round(prev_3m, 2),
            "delta_pct": delta_pct,
        }

    logger.info(
        "Metrics computed: income=%.2f expense=%.2f avg_monthly=%.2f categories=%d",
        total_income, total_expense, avg_monthly_expense, len(category_breakdown),
    )

    return {
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "avg_monthly_expense": avg_monthly_expense,
        "category_breakdown": category_breakdown,
        "trend": trend,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Utility
# ──────────────────────────────────────────────────────────────────────────────

def _subtract_months(d: date, months: int) -> date:
    """Return a date that is ``months`` calendar months before ``d``."""
    month = d.month - months
    year = d.year
    while month <= 0:
        month += 12
        year -= 1
    # Clamp day to the last valid day of the target month
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))