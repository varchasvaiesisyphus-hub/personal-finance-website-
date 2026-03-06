"""
ai_pipeline/tests/test_insights_api.py

Tests for GET /api/ai/insights/latest/ and POST /api/ai/insights/<pk>/feedback/
All tests are offline — no network calls.
"""
from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from ai_pipeline.models import AIInsight


def _make_user(username: str, password: str = "pass1234") -> User:
    return User.objects.create_user(username=username, password=password)


def _make_insight(user: User, action: str = "Test action", confidence: str = "medium") -> AIInsight:
    return AIInsight.objects.create(
        user=user,
        action=action,
        explanation="Test explanation",
        estimated_monthly_saving=500.0,
        confidence=confidence,
        next_step="Do something",
        tags=["test"],
    )


class TestLatestInsightsEndpoint(TestCase):

    def setUp(self):
        self.user = _make_user("alice")
        self.other = _make_user("bob")
        self.client = Client()

    def test_requires_authentication(self):
        response = self.client.get("/api/ai/insights/latest/")
        # Redirects to login
        self.assertIn(response.status_code, (302, 401, 403))

    def test_returns_only_own_insights(self):
        _make_insight(self.user, "Alice insight")
        _make_insight(self.other, "Bob insight")

        self.client.login(username="alice", password="pass1234")
        response = self.client.get("/api/ai/insights/latest/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("insights", data)
        actions = [i["action"] for i in data["insights"]]
        self.assertIn("Alice insight", actions)
        self.assertNotIn("Bob insight", actions)

    def test_returns_at_most_3(self):
        for i in range(5):
            _make_insight(self.user, f"Insight {i}")

        self.client.login(username="alice", password="pass1234")
        response = self.client.get("/api/ai/insights/latest/")
        data = response.json()
        self.assertLessEqual(len(data["insights"]), 3)

    def test_returns_empty_list_when_no_insights(self):
        self.client.login(username="alice", password="pass1234")
        response = self.client.get("/api/ai/insights/latest/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["insights"], [])

    def test_response_shape(self):
        _make_insight(self.user)
        self.client.login(username="alice", password="pass1234")
        response = self.client.get("/api/ai/insights/latest/")
        insight = response.json()["insights"][0]
        for field in ("id", "action", "explanation", "estimated_monthly_saving",
                      "confidence", "next_step", "tags", "feedback"):
            self.assertIn(field, insight)

    def test_excludes_draft_pipeline_output(self):
        """Milestone 2 draft rows should not appear in the Garvis UI."""
        AIInsight.objects.create(user=self.user, action="draft_pipeline_output")
        _make_insight(self.user, "Real suggestion")
        self.client.login(username="alice", password="pass1234")
        response = self.client.get("/api/ai/insights/latest/")
        actions = [i["action"] for i in response.json()["insights"]]
        self.assertNotIn("draft_pipeline_output", actions)
        self.assertIn("Real suggestion", actions)


class TestFeedbackEndpoint(TestCase):

    def setUp(self):
        self.user = _make_user("carol")
        self.other = _make_user("dave")
        self.client = Client()

    def test_requires_authentication(self):
        insight = _make_insight(self.user)
        response = self.client.post(
            f"/api/ai/insights/{insight.pk}/feedback/",
            data=json.dumps({"feedback": "accept"}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (302, 401, 403))

    def test_accept_feedback(self):
        insight = _make_insight(self.user)
        self.client.login(username="carol", password="pass1234")
        response = self.client.post(
            f"/api/ai/insights/{insight.pk}/feedback/",
            data=json.dumps({"feedback": "accept"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        insight.refresh_from_db()
        self.assertEqual(insight.feedback, "accept")

    def test_reject_feedback(self):
        insight = _make_insight(self.user)
        self.client.login(username="carol", password="pass1234")
        self.client.post(
            f"/api/ai/insights/{insight.pk}/feedback/",
            data=json.dumps({"feedback": "reject"}),
            content_type="application/json",
        )
        insight.refresh_from_db()
        self.assertEqual(insight.feedback, "reject")

    def test_cannot_feedback_other_users_insight(self):
        other_insight = _make_insight(self.other, "Other's insight")
        self.client.login(username="carol", password="pass1234")
        response = self.client.post(
            f"/api/ai/insights/{other_insight.pk}/feedback/",
            data=json.dumps({"feedback": "accept"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        other_insight.refresh_from_db()
        self.assertIsNone(other_insight.feedback)

    def test_invalid_feedback_value_rejected(self):
        insight = _make_insight(self.user)
        self.client.login(username="carol", password="pass1234")
        response = self.client.post(
            f"/api/ai/insights/{insight.pk}/feedback/",
            data=json.dumps({"feedback": "maybe"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_nonexistent_insight_returns_404(self):
        self.client.login(username="carol", password="pass1234")
        response = self.client.post(
            "/api/ai/insights/99999/feedback/",
            data=json.dumps({"feedback": "accept"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)