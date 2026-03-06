"""
ai_pipeline/services/representative.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Select up to 8 representative transactions from sanitised output.

Selection strategy (priority order — deterministic):
1. **Recurring** transactions (pick the most-recent per recurring merchant, up to 2).
2. **Anomalous** transactions (highest anomaly score, up to 2).
3. **Top-expense** transactions (highest amount in the window, up to 2).
4. **Most-recent** transactions (latest dates not already selected, up to 2).

Deduplication is by transaction_id (or by date+amount if id is None).
The final list is sorted by date descending, then amount descending.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from ai_pipeline.services.sanitizer import SanitisedTransaction

logger = logging.getLogger(__name__)

MAX_REPRESENTATIVE = 8
_SLOTS_PER_TIER = 2


def select_representative(
    sanitised: List[SanitisedTransaction],
    recurring: List[Dict[str, Any]],
    anomalies: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Pick up to MAX_REPRESENTATIVE transactions.

    Parameters
    ----------
    sanitised : all sanitised transactions for the window
    recurring : output of detect_recurring()
    anomalies : output of detect_anomalies()

    Returns
    -------
    List of dicts matching the ``representative_transactions`` schema.
    """
    logger.info(
        "Selecting representative transactions from %d sanitised items", len(sanitised)
    )

    seen_ids: Set[Any] = set()
    selected: List[SanitisedTransaction] = []

    def _uid(st: SanitisedTransaction) -> Any:
        return st.transaction_id if st.transaction_id is not None else (st.date, st.amount)

    def _try_add(st: SanitisedTransaction) -> bool:
        uid = _uid(st)
        if uid in seen_ids:
            return False
        seen_ids.add(uid)
        selected.append(st)
        return True

    def _lookup_by_id(tx_id: Any) -> SanitisedTransaction | None:
        if tx_id is None:
            return None
        for st in sanitised:
            if st.transaction_id == tx_id:
                return st
        return None

    # ── Tier 1: Recurring (most-recent per merchant) ────────────────────────
    # Build set of normalised merchants from the recurring output
    seen_merchants: Set[str] = set()
    # Sort sanitised by date desc for recency
    date_sorted = sorted(sanitised, key=lambda s: (s.date, s.amount), reverse=True)
    recurring_merchants = {r["normalized_merchant"] for r in recurring}

    tier1_count = 0
    for st in date_sorted:
        if tier1_count >= _SLOTS_PER_TIER:
            break
        from ai_pipeline.services.recurring import _normalise_merchant
        norm = _normalise_merchant(st.merchant)
        if norm in recurring_merchants and norm not in seen_merchants:
            seen_merchants.add(norm)
            if _try_add(st):
                tier1_count += 1

    # ── Tier 2: Anomalous (highest score) ──────────────────────────────────
    tier2_count = 0
    for anom in anomalies:
        if tier2_count >= _SLOTS_PER_TIER:
            break
        tx_id = anom.get("transaction_id")
        st = _lookup_by_id(tx_id)
        if st and _try_add(st):
            tier2_count += 1

    # ── Tier 3: Top-expense (highest amounts, expense only) ─────────────────
    expense_sorted = sorted(
        [s for s in sanitised],
        key=lambda s: (-s.amount, s.date),
    )
    tier3_count = 0
    for st in expense_sorted:
        if tier3_count >= _SLOTS_PER_TIER:
            break
        if _try_add(st):
            tier3_count += 1

    # ── Tier 4: Most-recent (any type) ─────────────────────────────────────
    tier4_count = 0
    for st in date_sorted:
        if len(selected) >= MAX_REPRESENTATIVE:
            break
        if tier4_count >= _SLOTS_PER_TIER:
            break
        if _try_add(st):
            tier4_count += 1

    # ── Final sort: date desc, amount desc ──────────────────────────────────
    selected.sort(key=lambda s: (s.date, s.amount), reverse=True)
    selected = selected[:MAX_REPRESENTATIVE]

    result = [
        {
            "date": s.date,
            "amount": round(s.amount, 2),
            "merchant": s.merchant,
            "category": s.category,
            "sanitized_description": s.sanitized_description,
        }
        for s in selected
    ]

    logger.info("Selected %d representative transactions", len(result))
    return result