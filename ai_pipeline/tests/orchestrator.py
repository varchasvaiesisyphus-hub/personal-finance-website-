"""Tests for ai_pipeline/services/orchestrator.py"""

from __future__ import annotations

import json

from django.test import TestCase

from ai_pipeline.services.orchestrator import prepare_user_payload
from ai_pipeline.tests._factories import make_category, make_transaction, make_user


class OrchestratorTest(TestCase):
    def setUp(self):
        self.user = make_user("orch_user")
        self.cat_food = make_category(self.user, "Food")
        self.cat_salary = make_category(self.user, "Salary", "income")
        # Seed some transactions
        for i in range(5):
            make_transaction(self.user, self.cat_food, 100 + i * 10, days_ago=i * 5)
        make_transaction(self.user, self.cat_salary, 50000, days_ago=10, tx_type="income")

    def test_payload_schema(self):
        payload = prepare_user_payload(self.user, days=90)

        self.assertIn("user_id", payload)
        self.assertIn("start_date", payload)
        self.assertIn("end_date", payload)
        self.assertIn("metrics", payload)
        self.assertIn("recurring", payload)
        self.assertIn("anomalies", payload)
        self.assertIn("representative_transactions", payload)
        self.assertIn("sanitization_log", payload)
        self.assertIn("meta", payload)

    def test_metrics_populated(self):
        payload = prepare_user_payload(self.user, days=90)
        m = payload["metrics"]
        self.assertIn("total_income", m)
        self.assertIn("total_expense", m)
        self.assertIn("avg_monthly_expense", m)
        self.assertIn("category_breakdown", m)
        self.assertIn("trend", m)
        self.assertGreater(m["total_expense"], 0)
        self.assertGreater(m["total_income"], 0)

    def test_json_serialisable(self):
        payload = prepare_user_payload(self.user, days=90)
        # Must not raise
        dumped = json.dumps(payload)
        self.assertIsInstance(dumped, str)

    def test_user_id_matches(self):
        payload = prepare_user_payload(self.user, days=90)
        self.assertEqual(payload["user_id"], self.user.pk)

    def test_representative_max_8(self):
        payload = prepare_user_payload(self.user, days=90)
        self.assertLessEqual(len(payload["representative_transactions"]), 8)

    def test_ai_disabled_short_circuits(self):
        from ai_pipeline.models import AIPreferences
        AIPreferences.objects.create(user=self.user, ai_enabled=False)
        payload = prepare_user_payload(self.user, days=90)
        # When disabled the pipeline should return empty lists / dicts
        self.assertEqual(payload["recurring"], [])
        self.assertEqual(payload["anomalies"], [])
        self.assertEqual(payload["representative_transactions"], [])
        self.assertFalse(payload["meta"].get("ai_enabled", True))

    def test_meta_fields(self):
        payload = prepare_user_payload(self.user, days=90)
        self.assertEqual(payload["meta"]["days"], 90)
        self.assertIn("computed_at", payload["meta"])

    def test_no_transactions(self):
        empty_user = make_user("empty_orch")
        payload = prepare_user_payload(empty_user, days=90)
        self.assertEqual(payload["metrics"]["total_expense"], 0.0)
        self.assertEqual(payload["recurring"], [])
        self.assertEqual(payload["anomalies"], [])