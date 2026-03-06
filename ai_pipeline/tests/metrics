"""Tests for ai_pipeline/services/metrics.py"""

from __future__ import annotations

from datetime import date, timedelta

from django.test import TestCase

from ai_pipeline.services.metrics import compute_metrics
from ai_pipeline.tests._factories import make_category, make_transaction, make_user


class MetricsBasicTest(TestCase):
    def setUp(self):
        self.user = make_user("metrics_user")
        self.cat_food = make_category(self.user, "Food")
        self.cat_salary = make_category(self.user, "Salary", "income")

    def _window(self, days: int = 90):
        end = date.today()
        start = end - timedelta(days=days)
        return start, end

    def test_total_income_and_expense(self):
        make_transaction(self.user, self.cat_salary, 5000, days_ago=10, tx_type="income")
        make_transaction(self.user, self.cat_food,   1000, days_ago=5)
        make_transaction(self.user, self.cat_food,   500,  days_ago=3)

        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        start, end = self._window()
        result = compute_metrics(self.user, txns, start, end)

        self.assertAlmostEqual(result["total_income"], 5000.0, places=2)
        self.assertAlmostEqual(result["total_expense"], 1500.0, places=2)

    def test_category_breakdown(self):
        cat_rent = make_category(self.user, "Rent")
        make_transaction(self.user, self.cat_food, 200, days_ago=5)
        make_transaction(self.user, self.cat_food, 300, days_ago=10)
        make_transaction(self.user, cat_rent, 1000, days_ago=2)

        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        start, end = self._window()
        result = compute_metrics(self.user, txns, start, end)

        self.assertAlmostEqual(result["category_breakdown"]["Food"], 500.0, places=2)
        self.assertAlmostEqual(result["category_breakdown"]["Rent"], 1000.0, places=2)

    def test_avg_monthly_expense(self):
        """avg_monthly_expense = total_expense / distinct_months_with_activity"""
        # Create expenses in two distinct months
        make_transaction(self.user, self.cat_food, 600, days_ago=35)  # ~1 month ago
        make_transaction(self.user, self.cat_food, 400, days_ago=5)   # this month

        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        start, end = self._window(days=90)
        result = compute_metrics(self.user, txns, start, end)

        # Two distinct months → avg = 1000 / 2 = 500
        self.assertAlmostEqual(result["avg_monthly_expense"], 500.0, places=2)

    def test_trend_has_correct_keys(self):
        make_transaction(self.user, self.cat_food, 300, days_ago=5)
        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        start, end = self._window()
        result = compute_metrics(self.user, txns, start, end)

        for cat_name, trend_val in result["trend"].items():
            self.assertIn("last_3m", trend_val)
            self.assertIn("prev_3m", trend_val)
            self.assertIn("delta_pct", trend_val)

    def test_empty_transactions(self):
        start, end = self._window()
        result = compute_metrics(self.user, [], start, end)
        self.assertEqual(result["total_income"], 0.0)
        self.assertEqual(result["total_expense"], 0.0)
        self.assertEqual(result["category_breakdown"], {})

    def test_json_serialisable(self):
        import json
        make_transaction(self.user, self.cat_food, 100, days_ago=5)
        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        start, end = self._window()
        result = compute_metrics(self.user, txns, start, end)
        # Should not raise
        json.dumps(result)