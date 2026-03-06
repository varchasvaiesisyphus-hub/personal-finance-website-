"""
ai_pipeline/services/sanitizer.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
PII redaction and merchant normalisation.

Redacts:
  - Email addresses          → [EMAIL]
  - 10+ digit sequences      → [ACCOUNT_NUMBER]  (PAN, card, account numbers)
  - Phone-like patterns      → [PHONE]
  - UPI VPAs (user@bank)     → [UPI_VPA]

A ``sanitization_log`` dict tracks how many fields were changed and provides
redacted examples (at most 5 distinct patterns).

The sanitizer is PURE: it never writes to the database.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, NamedTuple, Optional

from core.models import Transaction

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Compiled patterns (order matters – applied left to right)
# ──────────────────────────────────────────────────────────────────────────────

_PATTERNS: List[tuple[re.Pattern, str]] = [
    # UPI VPA  e.g. user@upi, name@okicici – must come before generic email
    (re.compile(r"\b[a-zA-Z0-9.\-_+]+@(?:upi|okicici|okhdfcbank|okaxis|oksbi|ybl|ibl|rbl|apl|paytm|freecharge|mobikwik)\b", re.IGNORECASE), "[UPI_VPA]"),
    # Generic email
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    # 10+ consecutive digit sequence (card numbers, PAN, account numbers)
    (re.compile(r"\b\d{10,}\b"), "[ACCOUNT_NUMBER]"),
    # Phone: optional country code + 10 digits, with optional separators
    (re.compile(r"(?:\+91[\s\-]?)?[6-9]\d{9}\b"), "[PHONE]"),
    # Spaced credit-card style  e.g. 4321 1234 5678 9012
    (re.compile(r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}\b"), "[ACCOUNT_NUMBER]"),
]


class SanitisedTransaction(NamedTuple):
    """Lightweight view of a transaction after sanitisation."""
    transaction_id: Optional[int]
    date: str
    merchant: str
    category: str
    amount: float
    sanitized_description: str
    was_redacted: bool


# ──────────────────────────────────────────────────────────────────────────────
# Core redaction
# ──────────────────────────────────────────────────────────────────────────────

def _redact(text: str, examples: List[str]) -> tuple[str, bool]:
    """
    Apply all PII patterns to ``text``.  Returns (sanitised_text, changed).
    Appends up to 5 unique redaction examples to ``examples`` list.
    """
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


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def sanitize_transactions(
    transactions: List[Transaction],
) -> tuple[List[SanitisedTransaction], Dict[str, Any]]:
    """
    Sanitise a list of transactions in-memory.

    Returns
    -------
    sanitised : list of SanitisedTransaction namedtuples
    log       : dict with keys ``redacted_fields_count`` and ``redaction_examples``
    """
    logger.info("Sanitising %d transactions", len(transactions))

    sanitised: List[SanitisedTransaction] = []
    redacted_count = 0
    examples: List[str] = []

    for tx in transactions:
        raw_desc = getattr(tx, "description", "") or ""
        clean_desc, changed = _redact(raw_desc, examples)

        if changed:
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
                was_redacted=changed,
            )
        )

    log: Dict[str, Any] = {
        "redacted_fields_count": redacted_count,
        "redaction_examples": examples[:5],
    }

    logger.info("Sanitisation complete: %d fields redacted", redacted_count)
    return sanitised, log