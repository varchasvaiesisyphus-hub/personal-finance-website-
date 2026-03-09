"""
ai_pipeline/services/representative.py
Select up to 8 representative transactions. BUG 6 FIX: includes `reason` in output dict.
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

    # Tier 1: most-recent recurring
    date_sorted = sorted(sanitised, key=lambda s: (s.date, s.amount), reverse=True)
    recurring_merchants = {r["normalized_merchant"] for r in recurring}
    seen_merchants: Set[str] = set()
    tier1 = 0
    for st in date_sorted:
        if tier1 >= _SLOTS_PER_TIER:
            break
        from ai_pipeline.services.recurring import _normalise_merchant
        norm = _normalise_merchant(st.merchant)
        if norm in recurring_merchants and norm not in seen_merchants:
            seen_merchants.add(norm)
            if _try_add(st):
                tier1 += 1

    # Tier 2: anomalies
    tier2 = 0
    for anom in anomalies:
        if tier2 >= _SLOTS_PER_TIER:
            break
        st = _lookup_by_id(anom.get("transaction_id"))
        if st and _try_add(st):
            tier2 += 1

    # Tier 3: top expense
    tier3 = 0
    for st in sorted(sanitised, key=lambda s: (-s.amount, s.date)):
        if tier3 >= _SLOTS_PER_TIER:
            break
        if _try_add(st):
            tier3 += 1

    # Tier 4: most recent
    tier4 = 0
    for st in date_sorted:
        if len(selected) >= MAX_REPRESENTATIVE:
            break
        if tier4 >= _SLOTS_PER_TIER:
            break
        if _try_add(st):
            tier4 += 1

    selected.sort(key=lambda s: (s.date, s.amount), reverse=True)
    selected = selected[:MAX_REPRESENTATIVE]

    result = [
        {
            "date":                  s.date,
            "amount":                round(s.amount, 2),
            "merchant":              s.merchant,
            "category":              s.category,
            "reason":                s.reason,   # BUG 6 FIX: include reason
            "sanitized_description": s.sanitized_description,
        }
        for s in selected
    ]
    logger.info("Selected %d representative transactions", len(result))
    return result