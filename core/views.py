import datetime
import json

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Sum, Q
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .models import Category, Transaction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_transfer_category(category):
    """Return True when the category is the internal Transfer category."""
    return category.name == 'Transfer'


def _account_balance(user, account):
    income = Transaction.objects.filter(
        user=user, account=account, type='income'
    ).aggregate(t=Sum('amount'))['t'] or 0

    # Exclude Transfer-category transactions from expense totals
    expense = Transaction.objects.filter(
        user=user, account=account, type='expense'
    ).exclude(
        category__name='Transfer'
    ).aggregate(t=Sum('amount'))['t'] or 0

    # For balance purposes we still need raw transfers, so compute separately
    transfer_out = Transaction.objects.filter(
        user=user, account=account, type='expense', category__name='Transfer'
    ).aggregate(t=Sum('amount'))['t'] or 0

    transfer_in = Transaction.objects.filter(
        user=user, account=account, type='income', category__name='Transfer'
    ).aggregate(t=Sum('amount'))['t'] or 0

    return float(income + transfer_in - expense - transfer_out)


def _overall_balance(user):
    income = Transaction.objects.filter(
        user=user, type='income'
    ).aggregate(t=Sum('amount'))['t'] or 0

    expense = Transaction.objects.filter(
        user=user, type='expense'
    ).exclude(
        category__name='Transfer'
    ).aggregate(t=Sum('amount'))['t'] or 0

    # Transfers cancel each other out for overall balance (one expense = one income)
    return float(income - expense)


def _six_months_ago():
    today = datetime.date.today()
    return (today.replace(day=1) - datetime.timedelta(days=150)).replace(day=1)


def _fmt_monthly(qs):
    return [{'month': str(r['month'])[:7], 'total': float(r['total'])} for r in qs]


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------

@login_required
def home(request):
    transactions = Transaction.objects.filter(
        user=request.user
    ).select_related('category').order_by('-date', '-created_at')
    return render(request, 'index.html', {'transactions': transactions})


@login_required
def accounts(request):
    return render(request, 'Accounts.html')


@login_required
def transaction(request):
    transactions = Transaction.objects.filter(
        user=request.user
    ).select_related('category').order_by('-date', '-created_at')
    return render(request, 'transaction.html', {'transactions': transactions})


# ---------------------------------------------------------------------------
# Category API
# ---------------------------------------------------------------------------

@login_required
def api_categories(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        category = Category.objects.create(
            user=request.user,
            name=data['name'],
            type=data.get('type', 'expense'),
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


# ---------------------------------------------------------------------------
# Transaction API — create
# ---------------------------------------------------------------------------

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
        reason       = (payload.get('reason') or '').strip()

        if amount is None or date is None or not category_val:
            return JsonResponse(
                {'message': 'amount, date and category are required'}, status=400
            )

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
            reason=reason,
        )

        return JsonResponse({
            'id':       txn.id,
            'amount':   float(txn.amount),
            'date':     str(txn.date),
            'account':  txn.account,
            'category': cat.name,
            'type':     txn.type,
            'reason':   txn.reason,
        })
    except Exception as e:
        return JsonResponse({'message': str(e)}, status=400)


# ---------------------------------------------------------------------------
# Transaction API — edit
# ---------------------------------------------------------------------------

@require_http_methods(['POST'])
@login_required
def api_transaction_edit(request, pk):
    """
    PATCH-style endpoint: update an existing transaction in place.
    POST /api/transactions/<pk>/edit/
    Body: { amount, category, account, date, type, reason }
    Returns the updated transaction data.
    """
    user = request.user
    try:
        txn = Transaction.objects.select_related('category').get(pk=pk, user=user)
    except Transaction.DoesNotExist:
        return JsonResponse({'message': 'Transaction not found'}, status=404)

    try:
        payload      = json.loads(request.body)
        amount       = payload.get('amount')
        category_val = payload.get('category')
        account      = payload.get('account', txn.account)
        date         = payload.get('date', str(txn.date))
        txn_type     = payload.get('type', txn.type)
        reason       = (payload.get('reason') or '').strip()

        if amount is None or not category_val:
            return JsonResponse(
                {'message': 'amount and category are required'}, status=400
            )

        amount = float(amount)

        try:
            cat = Category.objects.get(id=category_val, user=user)
        except Category.DoesNotExist:
            return JsonResponse({'message': 'Invalid category'}, status=400)

        # Update fields
        txn.amount   = amount
        txn.category = cat
        txn.account  = account
        txn.date     = date
        txn.type     = txn_type
        txn.reason   = reason
        txn.save()

        return JsonResponse({
            'id':       txn.id,
            'amount':   float(txn.amount),
            'date':     str(txn.date),
            'account':  txn.account,
            'category': cat.name,
            'type':     txn.type,
            'reason':   txn.reason,
        })
    except Exception as e:
        return JsonResponse({'message': str(e)}, status=400)


# ---------------------------------------------------------------------------
# Transaction API — delete
# ---------------------------------------------------------------------------

@require_http_methods(['POST'])
@login_required
def api_delete_transactions(request):
    try:
        payload = json.loads(request.body)
        ids = payload.get('ids', [])
        if not ids:
            return JsonResponse({'message': 'No IDs provided'}, status=400)
        deleted_count, _ = Transaction.objects.filter(
            id__in=ids, user=request.user
        ).delete()
        return JsonResponse({'message': f'Deleted {deleted_count} transactions'})
    except Exception as e:
        return JsonResponse({'message': str(e)}, status=400)


# ---------------------------------------------------------------------------
# Balances
# ---------------------------------------------------------------------------

@login_required
def api_balances(request):
    user = request.user
    return JsonResponse({
        'cash':    _account_balance(user, 'cash'),
        'bank':    _account_balance(user, 'bank'),
        'savings': _account_balance(user, 'savings'),
        'overall': _overall_balance(user),
    })


# ---------------------------------------------------------------------------
# Transfer
# ---------------------------------------------------------------------------

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

        # Create both legs of the transfer
        Transaction.objects.create(
            user=user, category=transfer_cat,
            amount=amount, account=from_account,
            date=date, type='expense',
            reason=f'Transfer to {to_account.title()}',
        )
        Transaction.objects.create(
            user=user, category=transfer_cat,
            amount=amount, account=to_account,
            date=date, type='income',
            reason=f'Transfer from {from_account.title()}',
        )

        return JsonResponse({
            'message':     'Transfer successful',
            'new_balance': source_balance - amount,
        })
    except Exception as e:
        return JsonResponse({'message': str(e)}, status=400)


# ---------------------------------------------------------------------------
# Summary / dashboard
# ---------------------------------------------------------------------------

@login_required
def api_summary(request):
    user   = request.user
    cutoff = _six_months_ago()

    total_income = Transaction.objects.filter(
        user=user, type='income'
    ).aggregate(t=Sum('amount'))['t'] or 0

    # Exclude Transfer category from expense totals everywhere
    total_expense = Transaction.objects.filter(
        user=user, type='expense'
    ).exclude(
        category__name='Transfer'
    ).aggregate(t=Sum('amount'))['t'] or 0

    def monthly_qs(txn_type):
        qs = Transaction.objects.filter(
            user=user, type=txn_type, date__gte=cutoff
        )
        if txn_type == 'expense':
            qs = qs.exclude(category__name='Transfer')
        return (
            qs
            .annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )

    cat_expenses = (
        Transaction.objects
        .filter(user=user, type='expense')
        .exclude(category__name='Transfer')
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
                'reason':   t.reason,
            }
            for t in recent
        ],
    })


@login_required
def api_account_summary(request, account):
    if account not in ('cash', 'bank', 'savings'):
        return JsonResponse({'message': 'Unknown account'}, status=400)

    user   = request.user
    cutoff = _six_months_ago()

    inflow = Transaction.objects.filter(
        user=user, account=account, type='income'
    ).aggregate(t=Sum('amount'))['t'] or 0

    outflow = Transaction.objects.filter(
        user=user, account=account, type='expense'
    ).exclude(
        category__name='Transfer'
    ).aggregate(t=Sum('amount'))['t'] or 0

    def monthly_qs(txn_type):
        qs = Transaction.objects.filter(
            user=user, account=account, type=txn_type, date__gte=cutoff
        )
        if txn_type == 'expense':
            qs = qs.exclude(category__name='Transfer')
        return (
            qs
            .annotate(month=TruncMonth('date'))
            .values('month')
            .annotate(total=Sum('amount'))
            .order_by('month')
        )

    cat_expenses = (
        Transaction.objects
        .filter(user=user, account=account, type='expense')
        .exclude(category__name='Transfer')
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

    # For account balance, transfers do affect individual account balances
    transfer_out = Transaction.objects.filter(
        user=user, account=account, type='expense', category__name='Transfer'
    ).aggregate(t=Sum('amount'))['t'] or 0

    transfer_in = Transaction.objects.filter(
        user=user, account=account, type='income', category__name='Transfer'
    ).aggregate(t=Sum('amount'))['t'] or 0

    balance = float(inflow) + float(transfer_in) - float(outflow) - float(transfer_out)

    return JsonResponse({
        'account': account,
        'inflow':  float(inflow),
        'outflow': float(outflow),
        'balance': balance,
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
                'reason':   t.reason,
            }
            for t in recent
        ],
    })