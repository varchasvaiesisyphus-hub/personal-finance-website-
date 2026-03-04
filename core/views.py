from django.shortcuts import render
import json
from django.db.models import Sum
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import Category, Transaction
from django.contrib.auth.models import User


def _account_balance(user, account):
    """Return the net balance (income − expense) for a specific account."""
    income  = Transaction.objects.filter(user=user, account=account, type='income') \
                                  .aggregate(t=Sum('amount'))['t'] or 0
    expense = Transaction.objects.filter(user=user, account=account, type='expense') \
                                  .aggregate(t=Sum('amount'))['t'] or 0
    return float(income - expense)


def _overall_balance(user):
    """Return the net balance across all accounts."""
    income  = Transaction.objects.filter(user=user, type='income') \
                                  .aggregate(t=Sum('amount'))['t'] or 0
    expense = Transaction.objects.filter(user=user, type='expense') \
                                  .aggregate(t=Sum('amount'))['t'] or 0
    return float(income - expense)


@login_required
def home(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-date', '-created_at')
    return render(request, 'index.html', {'transactions': transactions})


@login_required
def accounts(request):
    return render(request, 'accounts.html')


@login_required
def api_categories(request):
    if request.method == "POST":
        data = json.loads(request.body)
        category = Category.objects.create(
            user=request.user,
            name=data["name"],
            type=data["type"]
        )
        return JsonResponse({"id": category.id, "name": category.name})

    elif request.method == "GET":
        categories = Category.objects.filter(user=request.user)
        return JsonResponse(
            [{"id": c.id, "name": c.name} for c in categories],
            safe=False
        )


# ── GET /api/balances/ ────────────────────────────────────────────────────────
@login_required
def api_balances(request):
    """Return per-account and overall net balances for the logged-in user."""
    user = request.user
    return JsonResponse({
        'cash':    _account_balance(user, 'cash'),
        'bank':    _account_balance(user, 'bank'),
        'overall': _overall_balance(user),
    })


# ── POST /api/transactions/ ───────────────────────────────────────────────────
@require_http_methods(["POST"])
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

        # ── Balance guard: block expense if it would exceed available funds ──
        if txn_type == 'expense':
            remaining = _overall_balance(user)
            if amount > remaining:
                return JsonResponse({
                    'message': (
                        f'Insufficient balance. '
                        f'Remaining: \u20b9{remaining:,.2f} — '
                        f'Expense: \u20b9{amount:,.2f}.'
                    )
                }, status=400)

        try:
            cat = Category.objects.get(id=category_val, user=user)
        except Category.DoesNotExist:
            return JsonResponse({'message': 'Invalid category'}, status=400)

        txn = Transaction.objects.create(
            user=user,
            category=cat,
            amount=amount,
            account=account,
            date=date,
            type=txn_type
        )

        return JsonResponse({
            'id':       txn.id,
            'amount':   float(txn.amount),
            'date':     str(txn.date),
            'account':  txn.account,
            'category': cat.name,
            'type':     txn.type
        })

    except Exception as e:
        return JsonResponse({'message': str(e)}, status=400)


# ── POST /api/transfer/ ───────────────────────────────────────────────────────
@require_http_methods(["POST"])
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
                status=400
            )

        amount = float(amount)
        if amount <= 0:
            return JsonResponse({'message': 'Amount must be positive'}, status=400)

        # ── Balance guard ──
        source_balance = _account_balance(user, from_account)
        if amount > source_balance:
            return JsonResponse({
                'message': (
                    f'Insufficient balance in {from_account.title()} account. '
                    f'Available: \u20b9{source_balance:,.2f}, '
                    f'Requested: \u20b9{amount:,.2f}.'
                )
            }, status=400)

        # Auto-create a shared "Transfer" category
        transfer_cat, _ = Category.objects.get_or_create(
            user=user,
            name='Transfer',
            defaults={'type': 'expense'}
        )

        # Debit source
        Transaction.objects.create(
            user=user, category=transfer_cat,
            amount=amount, account=from_account,
            date=date, type='expense'
        )
        # Credit destination
        Transaction.objects.create(
            user=user, category=transfer_cat,
            amount=amount, account=to_account,
            date=date, type='income'
        )

        return JsonResponse({
            'message':     'Transfer successful',
            'new_balance': source_balance - amount
        })

    except Exception as e:
        return JsonResponse({'message': str(e)}, status=400)


# ── POST /api/transactions/delete/ ───────────────────────────────────────────
@require_http_methods(["POST"])
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


# ── DELETE /api/categories/<pk>/ ─────────────────────────────────────────────
@require_http_methods(["DELETE"])
@login_required
def category_delete(request, pk):
    try:
        category = Category.objects.get(pk=pk, user=request.user)
        category.delete()
        return JsonResponse({"message": "Category deleted successfully"})
    except Category.DoesNotExist:
        return JsonResponse({"message": "Category not found"}, status=404)


@login_required
def transaction(request):
    transactions = Transaction.objects.filter(
        user=request.user
    ).order_by('-date', '-created_at')
    return render(request, 'transaction.html', {'transactions': transactions})