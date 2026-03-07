"""
core/management/commands/seed_dummy_data.py

Creates 6 months of realistic dummy transactions with detailed reason fields
so Garvis AI can generate personalised suggestions.

Usage:
    python manage.py seed_dummy_data --user 1
    python manage.py seed_dummy_data --username john
    python manage.py seed_dummy_data --user 1 --clear
"""

from __future__ import annotations

import calendar
import random
from datetime import date

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from core.models import Category, Transaction


# ── Transaction palettes ──────────────────────────────────────────────────────
# Format: (category_name, (min_amt, max_amt), reason, weight)

INCOME_PALETTE = [
    ("Salary",    (75000, 75000),  "Monthly salary credit",   1.0),
    ("Freelance", (8000,  22000),  "Freelance project payment", 0.3),
    ("Freelance", (5000,  12000),  "UI design contract",        0.2),
]

EXPENSE_PALETTE = [
    # Food — delivery apps (high weight, highly specific)
    ("Food", (220, 480),  "Swiggy order — biryani",          2.0),
    ("Food", (180, 420),  "Swiggy order — butter chicken",   1.5),
    ("Food", (200, 450),  "Swiggy order — dosa",             1.2),
    ("Food", (250, 550),  "Zomato order — pizza",            1.8),
    ("Food", (180, 380),  "Zomato order — shawarma",         1.4),
    ("Food", (200, 450),  "Zomato order — momos",            1.2),
    ("Food", (80,  160),  "Breakfast at office canteen",     2.5),
    ("Food", (120, 260),  "Lunch with colleagues",           2.5),
    ("Food", (180, 360),  "Dinner at restaurant",            1.5),
    ("Food", (300, 800),  "Weekend brunch",                  0.8),
    ("Food", (60,  130),  "Evening snacks",                  1.5),
    ("Food", (400, 900),  "Team lunch outing",               0.4),

    # Groceries
    ("Groceries", (900, 2200), "Weekly grocery run — DMart",        1.2),
    ("Groceries", (400, 950),  "Fruits and vegetables — local market", 1.0),
    ("Groceries", (600, 1500), "BigBasket monthly order",            0.8),
    ("Groceries", (300, 700),  "Zepto quick grocery delivery",       0.7),

    # Entertainment — subscriptions (specific service names)
    ("Entertainment", (199, 199), "Netflix subscription",            1.0),
    ("Entertainment", (119, 119), "Spotify Premium subscription",    1.0),
    ("Entertainment", (299, 299), "Amazon Prime subscription",       0.5),
    ("Entertainment", (179, 179), "YouTube Premium subscription",    0.4),
    ("Entertainment", (250, 500), "Movie tickets — PVR",             0.8),
    ("Entertainment", (350, 700), "Movie tickets — IMAX",            0.3),
    ("Entertainment", (500, 1200),"Concert tickets",                 0.15),
    ("Entertainment", (200, 400), "Board game café outing",          0.2),

    # Transport
    ("Transport", (80,  250),  "Uber ride to office",              3.0),
    ("Transport", (80,  200),  "Uber ride from office",            2.5),
    ("Transport", (60,  180),  "Ola auto to metro station",        2.0),
    ("Transport", (150, 350),  "Uber ride — late night",           1.0),
    ("Transport", (2000,3500), "Monthly fuel — petrol",            1.0),
    ("Transport", (150, 380),  "Rapido bike taxi",                 1.5),
    ("Transport", (500, 1200), "Ola outstation ride",              0.2),

    # Utilities
    ("Utilities", (800, 1400), "Electricity bill — BESCOM",        1.0),
    ("Utilities", (399, 599),  "Mobile recharge — Jio",           1.0),
    ("Utilities", (700, 1200), "Internet broadband — ACT Fibernet",1.0),
    ("Utilities", (200, 400),  "Water bill",                       0.8),
    ("Utilities", (600, 1000), "Gas cylinder refill",              0.7),

    # Health
    ("Health", (1200, 2500), "Gym membership — monthly",          1.0),
    ("Health", (300,  800),  "Pharmacy — medicines",              0.8),
    ("Health", (500,  2000), "Doctor consultation fee",           0.4),
    ("Health", (200,  500),  "Protein powder",                    0.5),
    ("Health", (400,  900),  "Yoga class — monthly pass",         0.3),

    # Shopping
    ("Shopping", (800,  3000), "Clothes shopping — Zara",         0.5),
    ("Shopping", (500,  2000), "Amazon order — electronics",      0.6),
    ("Shopping", (400,  1500), "Flipkart order — household items",0.5),
    ("Shopping", (1500, 5000), "Shoes — Nike",                    0.2),
    ("Shopping", (300,  800),  "Books — Amazon",                  0.4),
    ("Shopping", (600,  2500), "Myntra clothing haul",            0.3),

    # Personal Care
    ("Personal Care", (400, 900), "Haircut and styling",          0.8),
    ("Personal Care", (300, 700), "Skincare products",            0.5),
    ("Personal Care", (200, 500), "Salon — facial",               0.3),

    # Education
    ("Education", (999,  2999), "Udemy course — Python",          0.2),
    ("Education", (1500, 4999), "Coursera subscription",          0.15),

    # Social
    ("Social", (500, 1500), "Friend's birthday dinner",           0.4),
    ("Social", (300, 800),  "Gift for colleague",                 0.3),
    ("Social", (1000,3000), "Weekend trip expenses",              0.2),
]


def _weighted_sample(palette, n):
    items   = [p[:3] for p in palette]
    weights = [p[3] for p in palette]
    return random.choices(items, weights=weights, k=n)


def _random_date_in_month(year: int, month: int) -> date:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, random.randint(1, last))


class Command(BaseCommand):
    help = "Seed 6 months of realistic dummy transactions with reason fields."

    def add_arguments(self, parser):
        parser.add_argument("--user",     type=int, help="User PK")
        parser.add_argument("--username", type=str, help="Username")
        parser.add_argument("--clear",    action="store_true", default=False,
                            help="Delete existing transactions for this user first")

    def handle(self, *args, **options):
        # Resolve user
        if options.get("user"):
            try:
                user = User.objects.get(pk=options["user"])
            except User.DoesNotExist:
                raise CommandError(f"No user with pk={options['user']}")
        elif options.get("username"):
            try:
                user = User.objects.get(username=options["username"])
            except User.DoesNotExist:
                raise CommandError(f"No user with username={options['username']}")
        else:
            raise CommandError("Provide --user <pk> or --username <name>")

        self.stdout.write(f"Seeding dummy data for: {user.username} (pk={user.pk})")

        if options["clear"]:
            deleted, _ = Transaction.objects.filter(user=user).delete()
            self.stdout.write(self.style.WARNING(f"  Cleared {deleted} existing transactions."))

        # Ensure categories exist
        income_cat_names  = {row[0] for row in INCOME_PALETTE}
        expense_cat_names = {row[0] for row in EXPENSE_PALETTE}

        cat_map: dict[str, Category] = {}
        for name in income_cat_names:
            cat, _ = Category.objects.get_or_create(
                user=user, name=name, defaults={"type": "income"}
            )
            cat_map[name] = cat
        for name in expense_cat_names:
            if name not in cat_map:
                cat, _ = Category.objects.get_or_create(
                    user=user, name=name, defaults={"type": "expense"}
                )
                cat_map[name] = cat

        # Build 6 months (oldest → newest)
        today = date.today()
        months = []
        for i in range(6, 0, -1):
            m = today.month - i
            y = today.year
            while m <= 0:
                m += 12
                y -= 1
            months.append((y, m))

        created = 0

        for year, month in months:
            # Income
            for cat_name, amount_range, reason, weight in INCOME_PALETTE:
                if random.random() > weight:
                    continue
                amt = random.randint(*amount_range)
                # Salary always in first 5 days, freelance random
                if "salary" in reason.lower():
                    day = random.randint(1, 5)
                else:
                    day = random.randint(8, 28)
                last = calendar.monthrange(year, month)[1]
                txn_date = date(year, month, min(day, last))
                Transaction.objects.create(
                    user=user,
                    category=cat_map[cat_name],
                    type="income",
                    amount=amt,
                    account=random.choice(["bank", "savings"]),
                    date=txn_date,
                    reason=reason,
                )
                created += 1

            # Expenses: 30–45 per month
            for cat_name, amount_range, reason in _weighted_sample(EXPENSE_PALETTE, random.randint(30, 45)):
                amt      = round(random.uniform(*amount_range), 2)
                txn_date = _random_date_in_month(year, month)
                account  = random.choices(
                    ["cash", "bank", "bank", "savings"],
                    weights=[3, 5, 5, 1],
                )[0]
                Transaction.objects.create(
                    user=user,
                    category=cat_map[cat_name],
                    type="expense",
                    amount=amt,
                    account=account,
                    date=txn_date,
                    reason=reason,
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"  ✓ Created {created} transactions across {len(months)} months."
        ))
        self.stdout.write(
            f"  Next: python manage.py run_garvis --user {user.pk} --persist-insights"
        )