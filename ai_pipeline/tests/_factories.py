from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from core.models import Category, Transaction

def make_user(username: str = "testuser") -> User:
    return User.objects.create_user(username=username, password="x")

def make_category(user: User, name: str = "Food", cat_type: str = "expense") -> Category:
    return Category.objects.create(user=user, name=name, type=cat_type)

def make_transaction(user, category, amount, days_ago=0, tx_type="expense", description=""):
    tx_date = date.today() - timedelta(days=days_ago)
    return Transaction.objects.create(
        user=user, category=category,
        amount=Decimal(str(amount)), type=tx_type,
        date=tx_date, description=description, account="cash",
    )