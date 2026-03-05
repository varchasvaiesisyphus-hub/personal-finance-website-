from core.models import Transaction
from django.db.models import Sum
from datetime import datetime, timedelta


def calculate_user_metrics(user):
    """
    Computes spending metrics for the last 30 days
    """

    end_date = datetime.today()
    start_date = end_date - timedelta(days=30)

    transactions = Transaction.objects.filter(
        user=user,
        date__range=[start_date, end_date]
    )

    total_income = transactions.filter(
        transaction_type="income"
    ).aggregate(Sum("amount"))["amount__sum"] or 0

    total_expense = transactions.filter(
        transaction_type="expense"
    ).aggregate(Sum("amount"))["amount__sum"] or 0

    category_breakdown = {}

    for t in transactions.filter(transaction_type="expense"):
        category = t.category.name

        if category not in category_breakdown:
            category_breakdown[category] = 0

        category_breakdown[category] += float(t.amount)

    savings_rate = 0
    if total_income > 0:
        savings_rate = (total_income - total_expense) / total_income

    return {
        "total_income": float(total_income),
        "total_expense": float(total_expense),
        "savings_rate": savings_rate,
        "category_breakdown": category_breakdown,
    }

def main():
    print("Running recurring transaction detection")

if __name__ == "__main__":
    main()