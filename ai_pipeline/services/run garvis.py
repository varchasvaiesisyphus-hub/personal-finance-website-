"""
ai_pipeline/management/commands/run_garvis.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Management command: run_garvis --user <user_id>

Usage
-----
    python manage.py run_garvis --user 1
    python manage.py run_garvis --user 1 --days 60

Behaviour
---------
1. Calls ``prepare_user_payload`` for the given user.
2. Pretty-prints the JSON payload to stdout.
3. Persists a draft AIInsight row with action='draft_pipeline_output'.
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from ai_pipeline.models import AIInsight
from ai_pipeline.services.orchestrator import prepare_user_payload

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Garvis AI pipeline for a single user and persist a draft AIInsight."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=int,
            required=True,
            help="Primary key (id) of the User to process.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Look-back window in days (default: 90).",
        )

    def handle(self, *args, **options):
        user_id: int = options["user"]
        days: int = options["days"]

        # ── Fetch user ───────────────────────────────────────────────────────
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise CommandError(f"User with id={user_id} does not exist.")

        self.stdout.write(
            self.style.NOTICE(f"Running Garvis pipeline for user={user.username} (id={user_id}), days={days} …")
        )

        # ── Run pipeline ─────────────────────────────────────────────────────
        try:
            payload = prepare_user_payload(user, days=days)
        except Exception as exc:
            logger.exception("Pipeline failed for user=%s", user_id)
            raise CommandError(f"Pipeline failed: {exc}") from exc

        # ── Print payload ────────────────────────────────────────────────────
        self.stdout.write(json.dumps(payload, indent=2, default=str))

        # ── Persist draft AIInsight ──────────────────────────────────────────
        try:
            insight = AIInsight.objects.create(
                user=user,
                action=AIInsight.ACTION_DRAFT,
                payload=payload,
                days=days,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ AIInsight saved: id={insight.pk}, action='{insight.action}'"
                )
            )
        except Exception as exc:
            logger.exception("Failed to persist AIInsight for user=%s", user_id)
            self.stdout.write(
                self.style.WARNING(f"Warning: could not persist AIInsight — {exc}")
            )