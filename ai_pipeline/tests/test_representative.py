"""Tests for ai_pipeline/services/representative.py"""

from __future__ import annotations

from django.test import TestCase

from ai_pipeline.services.representative import select_representative, MAX_REPRESENTATIVE
from ai_pipeline.services.sanitizer import SanitisedTransaction


def _st(i: int, amount: float = 100.0, date_str: str = "2025-01-01") -> SanitisedTransaction:
    return SanitisedTransaction(
        transaction_id=i,
        date=date_str,
        merchant=f"Merchant{i}",
        category="Food",
        amount=amount,
        sanitized_description="",
        was_redacted=False,
    )


class RepresentativeSelectionTest(TestCase):
    def test_max_8_returned(self):
        """Never return more than MAX_REPRESENTATIVE items."""
        sanitised = [_st(i, amount=float(i * 100), date_str=f"2025-01-{i+1:02d}") for i in range(1, 20)]
        result = select_representative(sanitised, [], [])
        self.assertLessEqual(len(result), MAX_REPRESENTATIVE)

    def test_empty_input(self):
        result = select_representative([], [], [])
        self.assertEqual(result, [])

    def test_result_schema(self):
        sanitised = [_st(1, 200, "2025-01-05"), _st(2, 300, "2025-01-10")]
        result = select_representative(sanitised, [], [])
        for r in result:
            self.assertIn("date", r)
            self.assertIn("amount", r)
            self.assertIn("merchant", r)
            self.assertIn("category", r)
            self.assertIn("sanitized_description", r)

    def test_sorted_date_desc(self):
        sanitised = [
            _st(1, 100, "2025-01-01"),
            _st(2, 200, "2025-03-15"),
            _st(3, 150, "2025-02-20"),
        ]
        result = select_representative(sanitised, [], [])
        dates = [r["date"] for r in result]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_anomalous_transactions_included(self):
        """High-anomaly transactions should be prioritised."""
        sanitised = [_st(i, 100, "2025-01-01") for i in range(1, 5)]
        anomalies = [{"transaction_id": 3, "anomaly_score": 9.9}]
        result = select_representative(sanitised, [], anomalies)
        result_ids = [r["merchant"] for r in result]
        # Merchant3 should be present
        self.assertIn("Merchant3", result_ids)

    def test_no_duplicates(self):
        sanitised = [_st(i, float(i * 50), "2025-01-01") for i in range(1, 10)]
        result = select_representative(sanitised, [], [])
        merchants = [r["merchant"] for r in result]
        self.assertEqual(len(merchants), len(set(merchants)))