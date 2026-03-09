"""
ai_pipeline/tests/_factories.py

BUG 3 FIX: make_transaction now accepts a `reason` parameter.

Previously reason was never passed to Transaction.objects.create(), so every
test transaction had reason="" (empty string or field default). This meant:
  - _build_reason_breakdown() always returned {} for test payloads
  - The prompt's "EXACTLY WHAT THIS USER SPENDS ON" section always showed
    "(no reasons entered yet — give general advice based on categories)"
  - The key personalization feature of Garvis (naming real apps/services)
    was never exercised in any test

Now tests can pass reason="Swiggy order" etc. to exercise the full path.
"""
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from core.models import Category, Transaction


def make_user(username: str = "testuser") -> User:
    return User.objects.create_user(username=username, password="x")


def make_category(user: User, name: str = "Food", cat_type: str = "expense") -> Category:
    return Category.objects.create(user=user, name=name, type=cat_type)


def make_transaction(
    user: User,
    category: Category,
    amount: float,
    days_ago: int = 0,
    tx_type: str = "expense",
    description: str = "",
    reason: str = "",          # BUG 3 FIX: was missing; reason_breakdown always got {}
) -> Transaction:
    tx_date = date.today() - timedelta(days=days_ago)
    return Transaction.objects.create(
        user=user,
        category=category,
        amount=Decimal(str(amount)),
        type=tx_type,
        date=tx_date,
        description=description,
        reason=reason,          # BUG 3 FIX: now forwarded to the model
        account="cash",
    )