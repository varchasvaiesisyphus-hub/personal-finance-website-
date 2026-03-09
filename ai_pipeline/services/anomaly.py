"""
ai_pipeline/services/anomaly.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Category-aware anomaly detection using two complementary methods:

1. Z-score  – flags transactions whose amount is more than ``Z_THRESHOLD``
               standard deviations above the category mean.
2. MAD      – Median Absolute Deviation; more robust to outliers than z-score.
               A transaction is flagged if its modified Z-score > ``MAD_THRESHOLD``.

Both methods require at least ``MIN_SAMPLES`` transactions in the category to
produce a meaningful baseline.  For small groups a simple ratio test is used
(``RATIO_THRESHOLD`` × median).

Only *expense* transactions are analysed.

BUG 2 FIX: Removed _detect_for_group() which was dead code — detect_anomalies()
never called it and duplicated the logic inline.  Worse, the function's docstring
claimed it returned (z_score, mad_score, method) but it actually returned
(mean, (stdev, median, mad), "stat"), so any future caller would silently receive
wrong values.  The inline duplication in detect_anomalies() is correct and is kept.
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List

from core.models import Transaction

logger = logging.getLogger(__name__)

Z_THRESHOLD: float = 2.0        # Standard deviations above mean
MAD_THRESHOLD: float = 3.5      # Modified z-score threshold
RATIO_THRESHOLD: float = 3.0    # Fallback: amount > ratio * median
MIN_SAMPLES: int = 3            # Minimum group size for z-score / MAD


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _tx_amount(tx: Transaction) -> float:
    return round(float(getattr(tx, "amount", 0) or 0), 2)


def _tx_category(tx: Transaction) -> str:
    cat = getattr(tx, "category", None)
    if cat is not None:
        return str(getattr(cat, "name", cat))
    return getattr(tx, "category_name", "Unknown")


def _tx_merchant(tx: Transaction) -> str:
    merchant = getattr(tx, "merchant", None) or ""
    if not merchant.strip():
        cat = getattr(tx, "category", None)
        if cat is not None:
            merchant = str(getattr(cat, "name", cat))
        else:
            merchant = "unknown"
    return merchant


def _mad_zscore(value: float, median: float, mad: float) -> float:
    """Compute modified z-score using MAD.  Returns 0 if MAD is zero."""
    if mad == 0:
        return 0.0
    return abs(0.6745 * (value - median) / mad)


# NOTE: _detect_for_group() was removed in BUG 2 FIX.
# It was never called by detect_anomalies() (the logic is inlined below),
# and its return signature was wrong: docstring said (z_score, mad_score, method)
# but the implementation returned (mean, (stdev, median, mad), method).


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def detect_anomalies(transactions: List[Transaction]) -> List[Dict[str, Any]]:
    """
    Return a list of anomalous expense transactions.

    Each entry matches the ``anomalies`` schema:
    {
      "transaction_id": int | null,
      "date": str,
      "merchant": str,
      "category": str,
      "amount": float,
      "anomaly_score": float,
      "reason": str,
    }
    Sorted by anomaly_score descending (most anomalous first).
    """
    logger.info("Running anomaly detection on %d transactions", len(transactions))

    # Only expense transactions
    expense_txns = [tx for tx in transactions if (getattr(tx, "type", "expense") or "expense") == "expense"]

    # Group amounts by category
    cat_groups: Dict[str, List[Transaction]] = defaultdict(list)
    for tx in expense_txns:
        cat_groups[_tx_category(tx)].append(tx)

    anomalies: List[Dict[str, Any]] = []

    for category, group in cat_groups.items():
        amounts = [_tx_amount(tx) for tx in group]
        n = len(amounts)

        if n < 2:
            # Can't compute baseline from a single transaction
            continue

        if n >= MIN_SAMPLES:
            mean = statistics.mean(amounts)
            stdev = statistics.pstdev(amounts)
            median = statistics.median(amounts)
            deviations = [abs(a - median) for a in amounts]
            mad = statistics.median(deviations)

            for tx in group:
                amt = _tx_amount(tx)
                z_score = abs((amt - mean) / stdev) if stdev > 0 else 0.0
                mad_score = _mad_zscore(amt, median, mad)

                score = round(max(z_score, mad_score), 4)

                if z_score >= Z_THRESHOLD or mad_score >= MAD_THRESHOLD:
                    reasons: List[str] = []
                    if z_score >= Z_THRESHOLD:
                        reasons.append(
                            f"z-score {z_score:.2f} ≥ {Z_THRESHOLD} "
                            f"(mean ₹{mean:.2f}, σ ₹{stdev:.2f})"
                        )
                    if mad_score >= MAD_THRESHOLD:
                        reasons.append(
                            f"MAD score {mad_score:.2f} ≥ {MAD_THRESHOLD} "
                            f"(median ₹{median:.2f}, MAD ₹{mad:.2f})"
                        )
                    _append_anomaly(anomalies, tx, category, amt, score, "; ".join(reasons))

        else:
            # Small group: use simple ratio to median
            median = statistics.median(amounts)
            for tx in group:
                amt = _tx_amount(tx)
                if median > 0 and amt > RATIO_THRESHOLD * median:
                    ratio = round(amt / median, 2)
                    score = round(ratio, 4)
                    reason = (
                        f"Amount ₹{amt:.2f} is {ratio}× the category median "
                        f"₹{median:.2f} (ratio threshold {RATIO_THRESHOLD})"
                    )
                    _append_anomaly(anomalies, tx, category, amt, score, reason)

    # Sort by anomaly_score descending, then by date, then by id for determinism
    anomalies.sort(key=lambda a: (-a["anomaly_score"], a["date"], a.get("transaction_id") or 0))

    logger.info("Anomaly detection found %d anomalies", len(anomalies))
    return anomalies


def _append_anomaly(
    lst: List[Dict[str, Any]],
    tx: Transaction,
    category: str,
    amount: float,
    score: float,
    reason: str,
) -> None:
    tx_date: date = getattr(tx, "date", None)
    lst.append({
        "transaction_id": getattr(tx, "pk", None),
        "date": str(tx_date) if tx_date else "",
        "merchant": _tx_merchant(tx),
        "category": category,
        "amount": round(amount, 2),
        "anomaly_score": score,
        "reason": reason,
    })