"""Tests for ai_pipeline/services/recurring.py"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.test import TestCase

from ai_pipeline.services.recurring import detect_recurring, _normalise_merchant
from ai_pipeline.tests._factories import make_category, make_transaction, make_user
from core.models import Transaction


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
        # Disconnect signals so test transaction creation doesn't fire the
        # AI pipeline in background threads and pollute the test environment.
        from core.signals import transaction_saved, transaction_deleted
        post_save.disconnect(transaction_saved, sender=Transaction)
        post_delete.disconnect(transaction_deleted, sender=Transaction)

        self.user = make_user("rec_user")
        self.cat = make_category(self.user, "Subscriptions")

    def tearDown(self):
        from core.signals import transaction_saved, transaction_deleted
        post_save.connect(transaction_saved, sender=Transaction)
        post_delete.connect(transaction_deleted, sender=Transaction)

    def test_monthly_cadence_detected(self):
        # 3 transactions ~30 days apart
        for i in range(3):
            make_transaction(self.user, self.cat, 999, days_ago=i * 30)

        txns = list(Transaction.objects.filter(user=self.user))
        result = detect_recurring(txns)

        self.assertTrue(len(result) >= 1)
        cadences = [r["cadence"] for r in result]
        self.assertIn("monthly", cadences)

    def test_non_recurring_not_detected(self):
        # Two transactions in the same category but very different amounts → different
        # amount buckets → each bucket has only 1 occurrence → nothing flagged.
        make_transaction(self.user, self.cat, 100,  days_ago=5)
        make_transaction(self.user, self.cat, 9999, days_ago=60)

        txns = list(Transaction.objects.filter(user=self.user))
        result = detect_recurring(txns)

        # FIX #6: The original assertion `self.assertEqual(r["count"], 1)` was
        # vacuous — detect_recurring filters out groups with < MIN_OCCURRENCES (2)
        # so a group of 1 is never included in the output.  The loop body never
        # ran, giving a false-green.  The correct assertion is that no recurring
        # groups are returned at all for this input.
        self.assertEqual(result, [], msg=(
            "Transactions with very different amounts should not be grouped "
            "as recurring (they land in different amount buckets)."
        ))

    def test_result_keys(self):
        for i in range(2):
            make_transaction(self.user, self.cat, 500, days_ago=i * 30)
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

        txns = list(Transaction.objects.filter(user=self.user))
        result = detect_recurring(txns)
        # Income transactions should not appear in recurring
        self.assertEqual(result, [])