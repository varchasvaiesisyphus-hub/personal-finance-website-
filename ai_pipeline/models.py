"""
ai_pipeline/models.py

Models for the AI pipeline app.
Updated for Milestone 3: AIInsight now carries all suggestion fields.
"""

from django.contrib.auth.models import User
from django.db import models


class AIPreferences(models.Model):
    """Per-user toggle for AI insight generation."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="ai_preferences")
    ai_enabled = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"AIPreferences(user={self.user_id}, enabled={self.ai_enabled})"


class AIInsight(models.Model):
    """
    A single persisted LLM-generated suggestion for a user.

    Milestone 2 used action/payload/days.
    Milestone 3 adds explanation, estimated_monthly_saving, confidence,
    next_step, tags so each row is self-contained.
    """

    CONFIDENCE_CHOICES = [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ai_insights")

    # ── Core suggestion fields (Milestone 3) ──
    action = models.CharField(max_length=255)
    explanation = models.TextField(blank=True, default="")
    estimated_monthly_saving = models.FloatField(null=True, blank=True)
    confidence = models.CharField(
        max_length=10, choices=CONFIDENCE_CHOICES, default="medium"
    )
    next_step = models.TextField(blank=True, default="")
    tags = models.JSONField(default=list)

    # ── Legacy Milestone 2 fields ──
    payload = models.JSONField(default=dict, blank=True)
    days = models.IntegerField(default=90)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"AIInsight(user={self.user_id}, action={self.action[:40]!r})"