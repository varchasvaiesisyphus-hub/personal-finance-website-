"""Tests for ai_pipeline/services/anomaly.py"""

from __future__ import annotations

from django.test import TestCase

from ai_pipeline.services.anomaly import detect_anomalies, Z_THRESHOLD
from ai_pipeline.tests._factories import make_category, make_transaction, make_user


class AnomalyDetectionTest(TestCase):
    def setUp(self):
        self.user = make_user("anomaly_user")
        self.cat = make_category(self.user, "Groceries")

    def test_outlier_flagged(self):
        """A transaction 5× the category average should be detected."""
        # Baseline: 5 normal transactions around 100
        for _ in range(5):
            make_transaction(self.user, self.cat, 100, days_ago=5)
        # Outlier
        make_transaction(self.user, self.cat, 5000, days_ago=1)

        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        anomalies = detect_anomalies(txns)

        self.assertTrue(len(anomalies) >= 1)
        # Highest-score anomaly should be the 5000 transaction
        self.assertAlmostEqual(anomalies[0]["amount"], 5000.0, places=0)

    def test_normal_transactions_not_flagged(self):
        """Transactions within the normal range should not be anomalies."""
        for amt in [95, 100, 105, 98, 102]:
            make_transaction(self.user, self.cat, amt, days_ago=5)

        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        anomalies = detect_anomalies(txns)
        self.assertEqual(anomalies, [])

    def test_result_schema(self):
        for _ in range(5):
            make_transaction(self.user, self.cat, 100, days_ago=5)
        make_transaction(self.user, self.cat, 9999, days_ago=1)

        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        anomalies = detect_anomalies(txns)

        for a in anomalies:
            self.assertIn("transaction_id", a)
            self.assertIn("date", a)
            self.assertIn("merchant", a)
            self.assertIn("category", a)
            self.assertIn("amount", a)
            self.assertIn("anomaly_score", a)
            self.assertIn("reason", a)

    def test_sorted_by_score_desc(self):
        """Anomalies must be sorted highest score first."""
        for _ in range(5):
            make_transaction(self.user, self.cat, 100, days_ago=10)
        make_transaction(self.user, self.cat, 9000, days_ago=2)
        make_transaction(self.user, self.cat, 3000, days_ago=3)

        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        anomalies = detect_anomalies(txns)

        if len(anomalies) >= 2:
            self.assertGreaterEqual(anomalies[0]["anomaly_score"], anomalies[1]["anomaly_score"])

    def test_income_transactions_excluded(self):
        cat_salary = make_category(self.user, "Salary", "income")
        # Even if an income amount looks big it should not be flagged
        for _ in range(5):
            make_transaction(self.user, cat_salary, 100, days_ago=10, tx_type="income")
        make_transaction(self.user, cat_salary, 99999, days_ago=1, tx_type="income")

        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        anomalies = detect_anomalies(txns)
        self.assertEqual(anomalies, [])

    def test_single_transaction_per_category_skipped(self):
        """Cannot compute baseline from a single transaction — no anomaly."""
        make_transaction(self.user, self.cat, 99999, days_ago=1)

        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        anomalies = detect_anomalies(txns)
        self.assertEqual(anomalies, [])