"""Tests for ai_pipeline/services/sanitizer.py"""

from __future__ import annotations

from django.test import TestCase

from ai_pipeline.services.sanitizer import sanitize_transactions, _redact
from ai_pipeline.tests._factories import make_category, make_transaction, make_user


class RedactFunctionTest(TestCase):
    def _redact(self, text: str) -> str:
        result, _ = _redact(text, [])
        return result

    def test_email_masked(self):
        out = self._redact("Contact me at user@example.com please")
        self.assertNotIn("user@example.com", out)
        self.assertIn("[EMAIL]", out)

    def test_account_number_masked(self):
        out = self._redact("Account 1234567890123456 was charged")
        self.assertNotIn("1234567890123456", out)
        self.assertIn("[ACCOUNT_NUMBER]", out)

    def test_phone_masked(self):
        out = self._redact("Call 9876543210 for details")
        self.assertNotIn("9876543210", out)
        self.assertIn("[PHONE]", out)

    def test_upi_masked(self):
        out = self._redact("Paid via user123@ybl")
        self.assertNotIn("user123@ybl", out)
        self.assertIn("[UPI_VPA]", out)

    def test_clean_text_unchanged(self):
        text = "Grocery shopping at the supermarket"
        out, changed = _redact(text, [])
        self.assertEqual(out, text)
        self.assertFalse(changed)

    def test_examples_collected(self):
        examples: list = []
        _redact("user@example.com called 9876543210", examples)
        self.assertGreater(len(examples), 0)


class SanitizeTransactionsTest(TestCase):
    def setUp(self):
        self.user = make_user("san_user")
        self.cat = make_category(self.user, "Bills")

    def test_pii_redacted_in_description(self):
        make_transaction(
            self.user, self.cat, 200, days_ago=5,
            description="Ref: 9876543210111213"
        )
        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        sanitised, log = sanitize_transactions(txns)

        self.assertEqual(len(sanitised), 1)
        self.assertNotIn("9876543210111213", sanitised[0].sanitized_description)
        self.assertEqual(log["redacted_fields_count"], 1)

    def test_clean_description_unchanged(self):
        make_transaction(self.user, self.cat, 100, days_ago=5, description="Monthly electricity bill")
        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        sanitised, log = sanitize_transactions(txns)

        self.assertEqual(sanitised[0].sanitized_description, "Monthly electricity bill")
        self.assertFalse(sanitised[0].was_redacted)
        self.assertEqual(log["redacted_fields_count"], 0)

    def test_log_has_correct_keys(self):
        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        _, log = sanitize_transactions(txns)
        self.assertIn("redacted_fields_count", log)
        self.assertIn("redaction_examples", log)

    def test_multiple_pii_same_field(self):
        make_transaction(
            self.user, self.cat, 300, days_ago=5,
            description="user@bank.com ref 12345678901234"
        )
        from core.models import Transaction
        txns = list(Transaction.objects.filter(user=self.user))
        sanitised, log = sanitize_transactions(txns)
        desc = sanitised[0].sanitized_description
        self.assertNotIn("@bank.com", desc)
        self.assertNotIn("12345678901234", desc)