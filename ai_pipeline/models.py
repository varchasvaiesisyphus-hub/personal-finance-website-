"""
Models for the AI pipeline app.

AIPreferences  – per-user opt-in/out flag.
AIInsight      – persisted pipeline output rows (draft or final).
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class AIPreferences(models.Model):
    """Stores per-user AI feature preferences."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="ai_preferences")
    ai_enabled = models.BooleanField(default=True, help_text="Allow the AI pipeline to process this user's data.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI Preference"
        verbose_name_plural = "AI Preferences"

    def __str__(self) -> str:
        status = "enabled" if self.ai_enabled else "disabled"
        return f"AIPreferences({self.user.username}, {status})"


class AIInsight(models.Model):
    """
    Persisted row produced by the orchestrator pipeline.
    The ``payload`` JSON field holds the full structured output
    (or a summarised version) ready for downstream LLM consumption.
    """

    ACTION_DRAFT = "draft_pipeline_output"
    ACTION_FINAL = "final_insight"

    ACTION_CHOICES = [
        (ACTION_DRAFT, "Draft Pipeline Output"),
        (ACTION_FINAL, "Final Insight"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ai_insights")
    action = models.CharField(max_length=64, choices=ACTION_CHOICES, default=ACTION_DRAFT)
    payload = models.JSONField(default=dict, help_text="Full or summarised orchestrator payload (JSON-serialisable).")
    days = models.PositiveIntegerField(default=90, help_text="Look-back window used when generating this insight.")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "AI Insight"
        verbose_name_plural = "AI Insights"

    def __str__(self) -> str:
        return f"AIInsight({self.user.username}, {self.action}, {self.created_at:%Y-%m-%d})"