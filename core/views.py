import datetime
import json

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .models import Category, Transaction


def _account_balance(user, account):
    income  = Transaction.objects.filter(user=user, account=account, type='income')\
                                  .aggregate(t=Sum('amount'))['t'] or 0
    expense = Transaction.objects.filter(user=user, account=account, type='expense')\
                                  .aggregate(t=Sum('amount'))['t'] or 0
    return float(income - expense)


def _overall_balance(user):
    income  = Transaction.objects.filter(user=user, type='income')\
                                  .aggregate(t=Sum('amount'))['t'] or 0
    expense = Transaction.objects.filter(user=user, type='expense')\
                                  .aggregate(t=Sum('amount'))['t'] or 0
    return float(income - expense)


def _six_months_ago():
    today = datetime.date.today()
    return (today.replace(day=1) - datetime.timedelta(days=150)).replace(day=1)


def _fmt_monthly(qs):
    return [{'month': str(r['month'])[:7], 'total': float(r['total'])} for r in qs]


# FIX #4: Map the period token sent by the Accounts page JS (7d, 30d, 1m, 6m, 1y)
# to a concrete cutoff date.  Previously _six_months_ago() was always used, so the
# period pills in the UI (7D / 30D / 1M / 6M / 1Y) had no effect on the chart data.
def _cutoff_for_period(period: str) -> datetime.date:
    today = datetime.date.today()
    period = (period or "6m").lower().strip()
    if period == "7d":
        return today - datetime.timedelta(days=7)
    if period == "30d":
        return today - datetime.timedelta(days=30)
    if period == "1m":
        # Calendar month boundary
        return (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    if period == "1y":
        return (today.replace(day=1) - datetime.timedelta(days=364)).replace(day=1)
    # Default / "6m"
    return _six_months_ago()


@login_required
def home(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-date', '-created_at')
    return render(request, 'index.html', {'transactions': transactions})


@login_required
def accounts(request):
    return render(request, 'Accounts.html')   # ← capital A, matches the actual file


@login_required
def transaction(request):
    transactions = Transaction.objects.filter(
        user=request.user
    ).order_by('-date', '-created_at')
    return render(request, 'transaction.html', {'transactions': transactions})


@login_required
def api_categories(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        category = Category.objects.create(
            user=request.user,
            name=data['name'],
            type=data['type'],
        )
        return JsonResponse({'id': category.id, 'name': category.name})

    categories = Category.objects.filter(user=request.user)
    return JsonResponse(
        [{'id': c.id, 'name': c.name} for c in categories],
        safe=False,
    )


@require_http_methods(['DELETE'])
@login_required
def category_delete(request, pk):
    try:
        category = Category.objects.get(pk=pk, user=request.user)
        category.delete()
        return JsonResponse({'message': 'Category deleted successfully'})
    except Category.DoesNotExist:
        return JsonResponse({'message': 'Category not found'}, status=404)


@require_http_methods(['POST'])
@login_required
def api_transactions(request):
    user = request.user
    try:
        payload      = json.loads(request.body)
        amount       = payload.get('amount')
        category_val = payload.get('category')
        account      = payload.get('account', 'cash')
        date         = payload.get('date')
        txn_type     = payload.get('type', 'expense')

        if amount is None or date is None or not category_val:
            return JsonResponse({'message': 'amount, date and category are required'}, status=400)

        amount = float(amount)

        if txn_type == 'expense':
            remaining = _overall_balance(user)
            if amount > remaining:
                return JsonResponse({
                    'message': (
                        f'Insufficient balance. '
                        f'Remaining: ₹{remaining:,.2f} — '
                        f'Expense: ₹{amount:,.2f}.'
                    )
                }, status=400)

        try:
            cat = Category.objects.get(id=category_val, user=user)
        except Category.DoesNotExist:
            return JsonResponse({'message': 'Invalid category'}, status=400)

        txn = Transaction.objects.create(
            user=user, category=cat, amount=amount,
            account=account, date=date, type=txn_type,
        )

        return JsonResponse({
            'id':       txn.id,
            'amount':   float(txn.amount),
            'date':     str(txn.date),
            'account':  txn.account,
            'category': cat.name,
            'type':     txn.type,
        })
    except Exception as e:
        return JsonResponse({'message': str(e)}, status=400)


@require_http_methods(['POST'])
@login_required
def api_delete_transactions(request):
    try:
        payload = json.loads(request.body)
        ids = payload.get('ids', [])
        if not ids:
            return JsonResponse({'message': 'No IDs provided'}, status=400)
        deleted_count, _ = Transaction.objects.filter(id__in=ids, user=request.user).delete()
        return JsonResponse({'message': f'Deleted {deleted_count} transactions'})
    except Exception as e:
        return JsonResponse({'message': str(e)}, status=400)


@login_required
def api_balances(request):
    user = request.user
    return JsonResponse({
        'cash':    _account_balance(user, 'cash'),
        'bank':    _account_balance(user, 'bank'),
        'savings': _account_balance(user, 'savings'),
        'overall': _overall_balance(user),
    })


@require_http_methods(['POST'])
@login_required
def api_transfer(request):
    user = request.user
    try:
        payload      = json.loads(request.body)
        from_account = payload.get('from_account', '').strip()
        to_account   = payload.get('to_account',   '').strip()
        amount       = payload.get('amount')
        date         = payload.get('date')

        if not all([from_account, to_account, amount, date]):
            return JsonResponse({'message': 'All fields are required'}, status=400)

        if from_account == to_account:
            return JsonResponse(
                {'message': 'Source and destination accounts must be different'},
                status=400,
            )

        amount = float(amount)
        if amount <= 0:
            return JsonResponse({'message': 'Amount must be positive'}, status=400)

        source_balance = _account_balance(user, from_account)
        if amount > source_balance:
            return JsonResponse({
                'message': (
                    f'Insufficient balance in {from_account.title()} account. '
                    f'Available: ₹{source_balance:,.2f}, '
                    f'Requested: ₹{amount:,.2f}.'
                )
            }, status=400)

        transfer_cat, _ = Category.objects.get_or_create(
            user=user, name='Transfer', defaults={'type': 'expense'},
        )

        Transaction.objects.create(
            user=user, category=transfer_cat,
            amount=amount, account=from_account,
            date=date, type='expense',
        )
        Transaction.objects.create(
            user=user, category=transfer_cat,
            amount=amount, account=to_account,
            date=date, type='income',
        )

        return JsonResponse({
            'message':     'Transfer successful',
            'new_balance': source_balance - amount,
        })
    except Exception as e:
        return JsonResponse({'message': str(e)}, status=400)


@login_required
def api_summary(request):
    user = request.user
    cutoff = _six_months_ago()

    total_income  = Transaction.objects.filter(user=user, type='income')\
                                        .aggregate(t=Sum('amount'))['t'] or 0
    total_expense = Transaction.objects.filter(user=user, type='expense')\
                                        .aggregate(t=Sum('amount'))['t'] or 0

    def monthly_qs(txn_type):
        return (
            Transaction.objects
            .filter(user=user, type=txn_type, date__gte=cutoff)
            .annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )

    cat_expenses = (
        Transaction.objects
        .filter(user=user, type='expense')
        .values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')[:8]
    )

    recent = (
        Transaction.objects
        .filter(user=user)
        .select_related('category')
        .order_by('-date', '-created_at')[:5]
    )

    return JsonResponse({
        'total_income':  float(total_income),
        'total_expense': float(total_expense),
        'balance':       float(total_income) - float(total_expense),
        'monthly_income':  _fmt_monthly(monthly_qs('income')),
        'monthly_expense': _fmt_monthly(monthly_qs('expense')),
        'category_expenses': [
            {'name': c['category__name'], 'total': float(c['total'])}
            for c in cat_expenses
        ],
        'recent_transactions': [
            {
                'date':     str(t.date),
                'category': t.category.name,
                'amount':   float(t.amount),
                'type':     t.type,
                'account':  t.account,
            }
            for t in recent
        ],
    })


@login_required
def api_account_summary(request, account):
    if account not in ('cash', 'bank', 'savings'):
        return JsonResponse({'message': 'Unknown account'}, status=400)

    user = request.user

    # FIX #4: Read the ?period= query param sent by the Accounts page JS.
    # Before this fix, _six_months_ago() was always used so the 7D / 30D / 1M /
    # 1Y period pills had no effect — they all showed the same 6-month chart.
    period = request.GET.get('period', '6m')
    cutoff = _cutoff_for_period(period)

    inflow  = Transaction.objects.filter(user=user, account=account, type='income')\
                                  .aggregate(t=Sum('amount'))['t'] or 0
    outflow = Transaction.objects.filter(user=user, account=account, type='expense')\
                                  .aggregate(t=Sum('amount'))['t'] or 0

    def monthly_qs(txn_type):
        return (
            Transaction.objects
            .filter(user=user, account=account, type=txn_type, date__gte=cutoff)
            .annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )

    cat_expenses = (
        Transaction.objects
        .filter(user=user, account=account, type='expense')
        .values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')[:6]
    )

    recent = (
        Transaction.objects
        .filter(user=user, account=account)
        .select_related('category')
        .order_by('-date', '-created_at')[:5]
    )

    return JsonResponse({
        'account': account,
        'inflow':  float(inflow),
        'outflow': float(outflow),
        'balance': float(inflow) - float(outflow),
        'monthly_income':  _fmt_monthly(monthly_qs('income')),
        'monthly_expense': _fmt_monthly(monthly_qs('expense')),
        'category_expenses': [
            {'name': c['category__name'], 'total': float(c['total'])}
            for c in cat_expenses
        ],
        'recent_transactions': [
            {
                'date':     str(t.date),
                'category': t.category.name,
                'amount':   float(t.amount),
                'type':     t.type,
            }
            for t in recent
        ],
    })