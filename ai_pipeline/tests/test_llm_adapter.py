"""
ai_pipeline/tests/test_llm_adapter.py

Unit tests for Milestone 3: LLM adapters, parser, and end-to-end insight generation.

All tests are fully offline — MockAdapter is used throughout, no network calls.
Run with:
    LLM_PROVIDER=mock python manage.py test ai_pipeline.tests.test_llm_adapter
"""

from __future__ import annotations

import json
import os
import re

os.environ.setdefault("LLM_PROVIDER", "mock")

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.test import TestCase, override_settings

from ai_pipeline.llm.llm_adapter import MockAdapter
from ai_pipeline.llm.parser import parse_llm_response
from ai_pipeline.llm.prompt_builder import build_prompt
from ai_pipeline.models import AIInsight
from core.models import Category, Transaction


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_user(username: str = "testuser") -> User:
    return User.objects.create_user(username=username, password="testpass123")


def _make_category(user: User, name: str = "Food", cat_type: str = "expense") -> Category:
    return Category.objects.create(user=user, name=name, type=cat_type)


def _make_transaction(
    user: User,
    category: Category,
    amount: float = 500.0,
    txn_type: str = "expense",
    date: str = "2025-01-15",
) -> Transaction:
    return Transaction.objects.create(
        user=user,
        category=category,
        amount=amount,
        type=txn_type,
        date=date,
        account="cash",
    )


# ─────────────────────────────────────────────────────────────────────────────
# MockAdapter tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMockAdapter(TestCase):
    """MockAdapter must return deterministic, schema-valid JSON."""

    def test_generate_returns_string(self):
        adapter = MockAdapter()
        result = adapter.generate(prompt="irrelevant", temperature=0.2, max_tokens=800)
        self.assertIsInstance(result, str)

    def test_generate_is_valid_json(self):
        adapter = MockAdapter()
        result = adapter.generate(prompt="irrelevant", temperature=0.2, max_tokens=800)
        parsed = json.loads(result)
        self.assertIn("suggestions", parsed)

    def test_generate_is_deterministic(self):
        """Same adapter always returns the same string."""
        adapter = MockAdapter()
        r1 = adapter.generate("p", 0.1, 100)
        r2 = adapter.generate("p", 0.1, 100)
        self.assertEqual(r1, r2)

    def test_generate_passes_parser(self):
        adapter = MockAdapter()
        raw = adapter.generate("p", 0.2, 800)
        parsed = parse_llm_response(raw)
        self.assertIn("suggestions", parsed)
        self.assertGreaterEqual(len(parsed["suggestions"]), 1)


# ─────────────────────────────────────────────────────────────────────────────
# Parser tests
# ─────────────────────────────────────────────────────────────────────────────

class TestParser(TestCase):
    """parse_llm_response must accept valid JSON and reject invalid."""

    _VALID = json.dumps({
        "suggestions": [
            {
                "action": "Cut subscriptions",
                "explanation": "You have duplicate streaming services.",
                "estimated_monthly_saving_in_inr": 500.0,
                "confidence": "high",
                "next_step": "Cancel one service this week.",
                "tags": ["subscriptions"],
            }
        ]
    })

    def test_accepts_valid_json(self):
        result = parse_llm_response(self._VALID)
        self.assertEqual(result["suggestions"][0]["action"], "Cut subscriptions")

    def test_accepts_json_with_preamble(self):
        """Handles models that add stray text before the JSON."""
        messy = "Sure! Here is the analysis:\n" + self._VALID + "\nHope that helps!"
        result = parse_llm_response(messy)
        self.assertIn("suggestions", result)

    def test_rejects_empty_string(self):
        with self.assertRaises(ValueError):
            parse_llm_response("")

    def test_rejects_plain_text(self):
        with self.assertRaises(ValueError):
            parse_llm_response("Here are my thoughts: spend less.")

    def test_rejects_wrong_confidence(self):
        bad = json.dumps({
            "suggestions": [
                {
                    "action": "x",
                    "explanation": "y",
                    "estimated_monthly_saving_in_inr": None,
                    "confidence": "VERY_HIGH",   # invalid enum
                    "next_step": "z",
                    "tags": [],
                }
            ]
        })
        with self.assertRaises(ValueError):
            parse_llm_response(bad)

    def test_rejects_missing_required_field(self):
        bad = json.dumps({
            "suggestions": [
                {
                    "action": "x",
                    # explanation missing
                    "estimated_monthly_saving_in_inr": None,
                    "confidence": "low",
                    "next_step": "z",
                    "tags": [],
                }
            ]
        })
        with self.assertRaises(ValueError):
            parse_llm_response(bad)

    def test_rejects_additional_properties(self):
        bad = json.dumps({
            "suggestions": [
                {
                    "action": "x",
                    "explanation": "y",
                    "estimated_monthly_saving_in_inr": None,
                    "confidence": "low",
                    "next_step": "z",
                    "tags": [],
                    "extra_field": "should not be here",
                }
            ]
        })
        with self.assertRaises(ValueError):
            parse_llm_response(bad)

    def test_null_saving_accepted(self):
        valid = json.dumps({
            "suggestions": [
                {
                    "action": "Build emergency fund",
                    "explanation": "No emergency savings detected.",
                    "estimated_monthly_saving_in_inr": None,
                    "confidence": "medium",
                    "next_step": "Open a separate savings account.",
                    "tags": ["savings", "emergency"],
                }
            ]
        })
        result = parse_llm_response(valid)
        self.assertIsNone(result["suggestions"][0]["estimated_monthly_saving_in_inr"])


# ─────────────────────────────────────────────────────────────────────────────
# Prompt builder tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPromptBuilder(TestCase):

    def test_build_prompt_contains_payload(self):
        """Prompt must contain the structured financial summary header and
        the JSON-only instruction — both are always present in the template."""
        payload = {"metrics": {}, "start_date": "2025-01-01", "end_date": "2025-03-31"}
        prompt = build_prompt(payload)
        self.assertIn("FINANCIAL SUMMARY", prompt)
        self.assertIn("RESPOND WITH VALID JSON ONLY", prompt)

    def test_build_prompt_compact_json(self):
        """Category breakdown amounts must appear in the prompt when supplied."""
        payload = {
            "metrics": {
                "total_income": 10000,
                "total_expense": 6000,
                "category_breakdown": {"Groceries": 3000, "Transport": 1500},
            }
        }
        prompt = build_prompt(payload)
        self.assertIn("Groceries", prompt)
        self.assertIn("Transport", prompt)


# ─────────────────────────────────────────────────────────────────────────────
# Integration test: generate_insights_for_user with MockAdapter
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(LLM_PROVIDER="mock")
class TestGenerateInsightsIntegration(TestCase):
    """End-to-end test using MockAdapter — no network, no API keys."""

    def setUp(self):
        os.environ["LLM_PROVIDER"] = "mock"
        self.user = _make_user("insightuser")

        # FIX #3: Disconnect the post_save / post_delete signals while running
        # these tests so that creating test transactions does NOT spawn background
        # threads that call generate_insights_for_user concurrently.  Without this
        # disconnect the background thread can (a) create AIInsight rows between
        # setUp() and the assertion, corrupting count checks, and (b) set the
        # garvis_hash cache before the test body runs, causing subsequent calls to
        # return {"status": "skipped"} instead of generating rows.
        from core.signals import transaction_saved, transaction_deleted
        post_save.disconnect(transaction_saved, sender=Transaction)
        post_delete.disconnect(transaction_deleted, sender=Transaction)

        cat = _make_category(self.user, "Groceries")
        # Create a few transactions so prepare_user_payload has data
        _make_transaction(self.user, cat, 1200.0, "expense", "2025-01-10")
        _make_transaction(self.user, cat, 950.0,  "expense", "2025-02-10")
        _make_transaction(self.user, cat, 200.0,  "income",  "2025-02-15")

        # FIX #2: Clear the per-user hash cache so every test starts clean.
        # The LocMemCache is NOT reset between test methods (unlike the DB which
        # is wrapped in a transaction), so a cache entry set by one test method
        # would cause the next method's generate_insights_for_user call to be
        # skipped as "data unchanged", silently breaking count assertions.
        cache.delete(f"garvis_hash_{self.user.pk}")
        cache.delete(f"garvis_insights_{self.user.pk}")

    def tearDown(self):
        # Re-connect signals so other test classes are not affected.
        from core.signals import transaction_saved, transaction_deleted
        post_save.connect(transaction_saved, sender=Transaction)
        post_delete.connect(transaction_deleted, sender=Transaction)

    def test_returns_ok_status(self):
        from ai_pipeline.insights import generate_insights_for_user
        result = generate_insights_for_user(self.user.pk)
        self.assertEqual(result["status"], "ok")

    def test_returns_saved_ids(self):
        from ai_pipeline.insights import generate_insights_for_user
        result = generate_insights_for_user(self.user.pk)
        self.assertIn("saved", result)
        self.assertIsInstance(result["saved"], list)
        self.assertGreaterEqual(len(result["saved"]), 1)

    def test_aiinsight_rows_created(self):
        from ai_pipeline.insights import generate_insights_for_user
        before = AIInsight.objects.filter(user=self.user).count()
        result = generate_insights_for_user(self.user.pk)
        after = AIInsight.objects.filter(user=self.user).count()
        self.assertEqual(after - before, len(result["saved"]))

    def test_insight_fields_populated(self):
        from ai_pipeline.insights import generate_insights_for_user
        generate_insights_for_user(self.user.pk)
        insight = AIInsight.objects.filter(user=self.user).first()
        self.assertIsNotNone(insight)
        self.assertGreater(len(insight.action), 0)
        self.assertIn(insight.confidence, ("high", "medium", "low"))
        self.assertIsInstance(insight.tags, list)

    def test_action_matches_mock_adapter_output(self):
        """The saved action text must match what MockAdapter returns."""
        from ai_pipeline.insights import generate_insights_for_user
        generate_insights_for_user(self.user.pk)
        actions = set(
            AIInsight.objects.filter(user=self.user).values_list("action", flat=True)
        )
        # MockAdapter always returns these two actions
        self.assertIn("Reduce dining out expenses", actions)
        self.assertIn("Cancel unused subscriptions", actions)

    def test_no_pii_in_explanation(self):
        """Net-zero PII: no email-like or long digit sequences in explanations."""
        from ai_pipeline.insights import generate_insights_for_user
        generate_insights_for_user(self.user.pk)
        email_re = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
        digit_re = re.compile(r"\d{10,}")
        for insight in AIInsight.objects.filter(user=self.user):
            self.assertIsNone(
                email_re.search(insight.explanation),
                f"Email found in explanation: {insight.explanation[:100]}",
            )
            self.assertIsNone(
                digit_re.search(insight.explanation),
                f"Long digit sequence found in explanation: {insight.explanation[:100]}",
            )

    def test_disabled_ai_preferences_short_circuits(self):
        from ai_pipeline.insights import generate_insights_for_user
        from ai_pipeline.models import AIPreferences
        AIPreferences.objects.create(user=self.user, ai_enabled=False)
        result = generate_insights_for_user(self.user.pk)
        self.assertEqual(result["status"], "disabled")
        # No new rows should have been created
        self.assertEqual(AIInsight.objects.filter(user=self.user).count(), 0)

    def test_idempotent_multiple_calls(self):
        """Each call with fresh cache must create new rows (no upsert)."""
        from ai_pipeline.insights import generate_insights_for_user

        generate_insights_for_user(self.user.pk)
        count1 = AIInsight.objects.filter(user=self.user).count()

        # FIX #2: The hash cache is populated after the first call.  Without
        # clearing it the second call would short-circuit and return
        # {"status": "skipped"}, making count2 == count1 and failing the
        # assertGreater below.  Clearing the cache forces a genuine second run.
        cache.delete(f"garvis_hash_{self.user.pk}")

        generate_insights_for_user(self.user.pk)
        count2 = AIInsight.objects.filter(user=self.user).count()
        self.assertGreater(count2, count1)