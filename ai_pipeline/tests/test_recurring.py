"""Tests for ai_pipeline/services/recurring.py"""

from __future__ import annotations

from django.test import TestCase

from ai_pipeline.services.recurring import detect_recurring, _normalise_merchant
from ai_pipeline.tests._factories import make_category, make_transaction, make_user


class NormaliseMerchantTest(TestCase):
    def test_lowercase(self):
        self.assertEqual(_normalise_merchant("Netflix"), "netflix")

    def test_strips_punctuation(self):
        self.assertEqual(_normalise_merchant("Amazon.in"), "amazon in")

    def test_collapses_whitespace(self):
        self.assertEqual(_normalise_merchant("  Foo   Bar  "), "foo bar")

    def test_empty_string(self):
        self.assertEqual(_normalise_merchant(""), "unknown")


class RecurringDetectionTest(TestCase):
    def setUp(self):
        self.user = make_user("rec_user")
        self.cat = make_category(self.user, "Subscriptions")

    def test_monthly_cadence_detected(self):
        # 3 transactions ~30 days apart
        for i in range(3):
            make_transaction(self.user, self.cat, 999, days_ago=i * 30)

        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        result = detect_recurring(txns)

        self.assertTrue(len(result) >= 1)
        cadences = [r["cadence"] for r in result]
        self.assertIn("monthly", cadences)

    def test_non_recurring_not_detected(self):
        # Each transaction on a very different amount or random spacing
        make_transaction(self.user, self.cat, 100, days_ago=5)
        make_transaction(self.user, self.cat, 9999, days_ago=60)

        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        result = detect_recurring(txns)
        # Two transactions in same category but very different amounts → different buckets
        # Expect 0 recurring (each bucket has only 1 occurrence)
        for r in result:
            self.assertEqual(r["count"], 1)  # not flagged as multi-occurrence

    def test_result_keys(self):
        for i in range(2):
            make_transaction(self.user, self.cat, 500, days_ago=i * 30)
        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        result = detect_recurring(txns)

        for r in result:
            self.assertIn("merchant", r)
            self.assertIn("normalized_merchant", r)
            self.assertIn("average_amount", r)
            self.assertIn("count", r)
            self.assertIn("cadence", r)
            self.assertIn("first_seen", r)
            self.assertIn("last_seen", r)

    def test_income_excluded(self):
        cat_salary = make_category(self.user, "Salary", "income")
        for i in range(3):
            make_transaction(self.user, cat_salary, 50000, days_ago=i * 30, tx_type="income")

        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        result = detect_recurring(txns)
        # Income transactions should not appear in recurring
        self.assertEqual(result, [])