"""
ai_pipeline/models.py  (Milestone 4 — adds feedback field)
"""
from django.contrib.auth.models import User
from django.db import models


class AIPreferences(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="ai_preferences")
    ai_enabled = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"AIPreferences(user={self.user_id}, enabled={self.ai_enabled})"


class AIInsight(models.Model):
    CONFIDENCE_CHOICES = [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]
    FEEDBACK_CHOICES = [
        ("accept", "accept"),
        ("reject", "reject"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ai_insights")

    # ── Milestone 3 suggestion fields ──
    action = models.CharField(max_length=255)
    explanation = models.TextField(blank=True, default="")
    estimated_monthly_saving = models.FloatField(null=True, blank=True)
    confidence = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES, default="medium")
    next_step = models.TextField(blank=True, default="")
    tags = models.JSONField(default=list)

    # ── Milestone 4: user feedback ──
    feedback = models.CharField(
        max_length=10, choices=FEEDBACK_CHOICES, null=True, blank=True
    )

    # ── Legacy Milestone 2 fields ──
    payload = models.JSONField(default=dict, blank=True)
    days = models.IntegerField(default=90)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"AIInsight(user={self.user_id}, action={self.action[:40]!r})"