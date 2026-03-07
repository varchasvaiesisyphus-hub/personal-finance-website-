"""
ai_pipeline/services/representative.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Select up to 8 representative transactions. Now includes the ``reason``
field in output so the prompt builder can reference real spending habits.
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
    logger.info("Selecting representative transactions from %d sanitised items", len(sanitised))

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

    seen_merchants: Set[str] = set()
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

    tier2_count = 0
    for anom in anomalies:
        if tier2_count >= _SLOTS_PER_TIER:
            break
        tx_id = anom.get("transaction_id")
        st = _lookup_by_id(tx_id)
        if st and _try_add(st):
            tier2_count += 1

    expense_sorted = sorted(sanitised, key=lambda s: (-s.amount, s.date))
    tier3_count = 0
    for st in expense_sorted:
        if tier3_count >= _SLOTS_PER_TIER:
            break
        if _try_add(st):
            tier3_count += 1

    tier4_count = 0
    for st in date_sorted:
        if len(selected) >= MAX_REPRESENTATIVE:
            break
        if tier4_count >= _SLOTS_PER_TIER:
            break
        if _try_add(st):
            tier4_count += 1

    selected.sort(key=lambda s: (s.date, s.amount), reverse=True)
    selected = selected[:MAX_REPRESENTATIVE]

    result = [
        {
            "date":                  s.date,
            "amount":                round(s.amount, 2),
            "merchant":              s.merchant,
            "category":              s.category,
            "reason":                s.reason,   # now included
            "sanitized_description": s.sanitized_description,
        }
        for s in selected
    ]

    logger.info("Selected %d representative transactions", len(result))
    return result