import uuid
from django.db import models
from django.contrib.auth.models import User


class AIInsight(models.Model):

    CONFIDENCE_LEVELS = [
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    action = models.CharField(max_length=255)

    explanation = models.TextField()

    estimated_monthly_saving = models.FloatField(
        null=True,
        blank=True
    )

    confidence = models.CharField(
        max_length=10,
        choices=CONFIDENCE_LEVELS
    )

    next_step = models.TextField()

    tags = models.JSONField(default=list)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.action}"


class AIPreferences(models.Model):

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    ai_enabled = models.BooleanField(default=True)

    monthly_saving_goal = models.FloatField(
        null=True,
        blank=True
    )

    excluded_merchants = models.JSONField(
        default=list,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"AI Preferences for {self.user.username}"