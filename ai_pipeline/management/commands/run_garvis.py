"""
ai_pipeline/management/commands/run_garvis.py

Management command for the AI pipeline.

Usage:
    # Run Milestone 2 pipeline only (draft payload):
    python manage.py run_garvis --user 1

    # Run Milestone 2 + persist Milestone 3 LLM insights:
    python manage.py run_garvis --user 1 --persist-insights

    # Custom lookback window:
    python manage.py run_garvis --user 1 --days 60 --persist-insights
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Garvis AI pipeline for a given user."

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=int,
            required=True,
            help="Primary key of the User to run the pipeline for.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Lookback window in days (default: 90).",
        )
        parser.add_argument(
            "--persist-insights",
            action="store_true",
            default=False,
            help=(
                "After generating the pipeline payload, call the LLM and persist "
                "AIInsight rows. Requires LLM_PROVIDER to be set (default: mock)."
            ),
        )

    def handle(self, *args, **options):
        user_id: int = options["user"]
        days: int = options["days"]
        persist: bool = options["persist_insights"]

        # ── Load user ──
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise CommandError(f"No User with pk={user_id} found.")

        # ── Milestone 2: pipeline payload ──
        from ai_pipeline.services.orchestrator import prepare_user_payload  # noqa: PLC0415

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Running Garvis pipeline for user '{user.username}' (days={days}) …"
        ))

        payload = prepare_user_payload(user, days=days)

        # Persist a draft AIInsight with the raw payload (Milestone 2 behaviour)
        from ai_pipeline.models import AIInsight  # noqa: PLC0415

        draft = AIInsight.objects.create(
            user=user,
            action="draft_pipeline_output",
            payload=payload,
            days=days,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Draft payload saved (AIInsight pk={draft.pk}).")
        )

        # Print compact JSON to stdout
        self.stdout.write(json.dumps(payload, indent=2, default=str))

        # ── Milestone 3: LLM insights (optional) ──
        if persist:
            self.stdout.write(
                self.style.MIGRATE_HEADING("Generating LLM insights (--persist-insights) …")
            )
            from ai_pipeline.insights import generate_insights_for_user  # noqa: PLC0415

            result = generate_insights_for_user(user_id)
            if result.get("status") == "disabled":
                self.stdout.write(self.style.WARNING(
                    "AI is disabled for this user — no insights generated."
                ))
            else:
                ids = result.get("saved", [])
                self.stdout.write(self.style.SUCCESS(
                    f"Persisted {len(ids)} insight(s): AIInsight pks = {ids}"
                ))