"""
ai_pipeline/services/sanitizer.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
PII redaction and merchant normalisation.

Now exposes the ``reason`` field on SanitisedTransaction so the pipeline
can forward it to the prompt builder for personalised suggestions.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, NamedTuple, Optional

from core.models import Transaction

logger = logging.getLogger(__name__)

_PATTERNS: List[tuple[re.Pattern, str]] = [
    (re.compile(r"\b[a-zA-Z0-9.\-_+]+@(?:upi|okicici|okhdfcbank|okaxis|oksbi|ybl|ibl|rbl|apl|paytm|freecharge|mobikwik)\b", re.IGNORECASE), "[UPI_VPA]"),
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}\b"), "[ACCOUNT_NUMBER]"),
    (re.compile(r"(?<!\d)(?:\+91[\s\-]?)?[6-9]\d{9}(?!\d)"), "[PHONE]"),
    (re.compile(r"\b\d{11,}\b"), "[ACCOUNT_NUMBER]"),
]


class SanitisedTransaction(NamedTuple):
    """Lightweight view of a transaction after sanitisation."""
    transaction_id: Optional[int]
    date: str
    merchant: str
    category: str
    amount: float
    sanitized_description: str
    reason: str           # user-entered reason, PII-redacted
    was_redacted: bool


def _redact(text: str, examples: List[str]) -> tuple[str, bool]:
    if not text:
        return text, False
    original = text
    for pattern, placeholder in _PATTERNS:
        matches = pattern.findall(text)
        for m in matches:
            if len(examples) < 5 and m not in examples:
                examples.append(m)
        text = pattern.sub(placeholder, text)
    return text, text != original


def _tx_merchant(tx: Transaction) -> str:
    merchant = getattr(tx, "merchant", None) or ""
    if not merchant.strip():
        cat = getattr(tx, "category", None)
        if cat is not None:
            merchant = str(getattr(cat, "name", cat))
        else:
            merchant = getattr(tx, "category_name", "unknown")
    return merchant


def _tx_category(tx: Transaction) -> str:
    cat = getattr(tx, "category", None)
    if cat is not None:
        return str(getattr(cat, "name", cat))
    return getattr(tx, "category_name", "Unknown")


def _tx_amount(tx: Transaction) -> float:
    return round(float(getattr(tx, "amount", 0) or 0), 2)


def sanitize_transactions(
    transactions: List[Transaction],
) -> tuple[List[SanitisedTransaction], Dict[str, Any]]:
    logger.info("Sanitising %d transactions", len(transactions))

    sanitised: List[SanitisedTransaction] = []
    redacted_count = 0
    examples: List[str] = []

    for tx in transactions:
        raw_desc   = getattr(tx, "description", "") or ""
        raw_reason = getattr(tx, "reason", "") or ""

        clean_desc,   changed_desc   = _redact(raw_desc,   examples)
        clean_reason, changed_reason = _redact(raw_reason, examples)

        if changed_desc or changed_reason:
            redacted_count += 1

        tx_date = getattr(tx, "date", None)
        sanitised.append(
            SanitisedTransaction(
                transaction_id=getattr(tx, "pk", None),
                date=str(tx_date) if tx_date else "",
                merchant=_tx_merchant(tx),
                category=_tx_category(tx),
                amount=_tx_amount(tx),
                sanitized_description=clean_desc,
                reason=clean_reason,
                was_redacted=changed_desc or changed_reason,
            )
        )

    log: Dict[str, Any] = {
        "redacted_fields_count": redacted_count,
        "redaction_examples":    examples[:5],
    }

    logger.info("Sanitisation complete: %d fields redacted", redacted_count)
    return sanitised, log