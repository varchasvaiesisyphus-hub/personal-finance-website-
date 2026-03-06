"""
ai_pipeline/services/recurring.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Detect recurring / subscription transactions using merchant normalisation
and cadence heuristics.

Approach
--------
1. Normalise the merchant name (lower-case, strip punctuation, collapse whitespace).
2. Group transactions by (normalised_merchant, rounded_amount).
3. For each group with 2+ occurrences, sort by date and inspect inter-event gaps:
   - Weekly:  mean gap  5 – 9 days
   - Monthly: mean gap 25 – 35 days
   - Annual:  mean gap 330 – 400 days
4. Return groups that match a cadence or have a suspiciously tight gap cluster.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional

from core.models import Transaction

logger = logging.getLogger(__name__)

# Amount bucket: round to nearest N units so small price fluctuations don't
# prevent grouping (e.g. ₹ 999 and ₹ 1001 → same bucket at granularity=10).
_AMOUNT_GRANULARITY = 10.0

# Minimum occurrences for a group to be flagged as recurring
_MIN_OCCURRENCES = 2


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _normalise_merchant(raw: str) -> str:
    """
    Return a canonical merchant key:
      - lowercase
      - remove punctuation (except spaces)
      - collapse whitespace
      - strip leading/trailing spaces
    """
    s = raw.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or "unknown"


def _bucket_amount(amount: float) -> float:
    """Round amount to nearest granularity bucket."""
    return round(round(amount / _AMOUNT_GRANULARITY) * _AMOUNT_GRANULARITY, 2)


def _detect_cadence(gaps_days: List[float]) -> Optional[str]:
    """
    Given a list of inter-event gaps (days), return cadence label or None.
    Uses mean gap for robustness.
    """
    if not gaps_days:
        return None
    mean_gap = sum(gaps_days) / len(gaps_days)
    if 5 <= mean_gap <= 9:
        return "weekly"
    if 25 <= mean_gap <= 35:
        return "monthly"
    if 330 <= mean_gap <= 400:
        return "annual"
    return None


def _tx_merchant(tx: Transaction) -> str:
    """Return raw merchant string, falling back to category name."""
    merchant = getattr(tx, "merchant", None) or ""
    if not merchant.strip():
        cat = getattr(tx, "category", None)
        if cat is not None:
            merchant = str(getattr(cat, "name", cat))
        else:
            merchant = getattr(tx, "category_name", "unknown")
    return merchant


def _tx_amount(tx: Transaction) -> float:
    return round(float(getattr(tx, "amount", 0) or 0), 2)


def _tx_date(tx: Transaction) -> date:
    return getattr(tx, "date", date.today())


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def detect_recurring(transactions: List[Transaction]) -> List[Dict[str, Any]]:
    """
    Analyse transactions and return a list of recurring-payment summaries.

    Each entry in the returned list matches the ``recurring`` schema:
    {
      "merchant": str,
      "normalized_merchant": str,
      "average_amount": float,
      "count": int,
      "cadence": "monthly" | "annual" | "weekly" | null,
      "first_seen": str,   # YYYY-MM-DD
      "last_seen": str,    # YYYY-MM-DD
    }
    """
    logger.info("Running recurring detection on %d transactions", len(transactions))

    # Only consider expense transactions for subscription detection
    expense_txns = [tx for tx in transactions if (getattr(tx, "type", "expense") or "expense") == "expense"]

    # Group by (normalised_merchant, amount_bucket)
    groups: Dict[tuple, List[Transaction]] = defaultdict(list)
    for tx in expense_txns:
        raw_merchant = _tx_merchant(tx)
        norm = _normalise_merchant(raw_merchant)
        bucket = _bucket_amount(_tx_amount(tx))
        groups[(norm, bucket)].append(tx)

    results: List[Dict[str, Any]] = []

    for (norm_merchant, _bucket), group in groups.items():
        if len(group) < _MIN_OCCURRENCES:
            continue

        # Sort by date ascending (deterministic)
        group_sorted = sorted(group, key=lambda tx: _tx_date(tx))
        dates = [_tx_date(tx) for tx in group_sorted]
        amounts = [_tx_amount(tx) for tx in group_sorted]

        # Compute inter-event gaps in days
        gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        cadence = _detect_cadence([float(g) for g in gaps])

        # Use raw merchant name from the most-recent transaction
        raw_merchant = _tx_merchant(group_sorted[-1])
        avg_amount = round(sum(amounts) / len(amounts), 2)

        results.append({
            "merchant": raw_merchant,
            "normalized_merchant": norm_merchant,
            "average_amount": avg_amount,
            "count": len(group),
            "cadence": cadence,
            "first_seen": str(dates[0]),
            "last_seen": str(dates[-1]),
        })

    # Sort deterministically: cadence first (monthly > annual > weekly > null),
    # then by count descending, then merchant name.
    _cadence_order = {"monthly": 0, "annual": 1, "weekly": 2, None: 3}
    results.sort(key=lambda r: (_cadence_order[r["cadence"]], -r["count"], r["normalized_merchant"]))

    logger.info("Recurring detection found %d groups", len(results))
    return results