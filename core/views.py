from django.shortcuts import render
import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from .models import Category, Transaction
from django.contrib.auth.models import User

@login_required
def home(request):
    # Fetch existing transactions for this user to show on load
    transactions = Transaction.objects.filter(user=request.user).order_by('-date')
    return render(request, 'index.html', {'transactions': transactions})
@login_required
def accounts(request):
    return render(request, 'accounts.html')

# core/views.py

@login_required
def api_categories(request):
    if request.method == "POST":
        data = json.loads(request.body)

        category = Category.objects.create(
            user=request.user,   # ← THIS IS REQUIRED
            name=data["name"],
            type=data["type"]
        )

        return JsonResponse({
            "id": category.id,
            "name": category.name
        })

    elif request.method == "GET":
        categories = Category.objects.filter(user=request.user)

        data = [
            {"id": c.id, "name": c.name}
            for c in categories
        ]

        return JsonResponse(data, safe=False)

@require_http_methods(["POST"])
@login_required
def api_transactions(request):
    user = request.user
    try:
        payload = json.loads(request.body)
        amount = payload.get('amount')
        category_val = payload.get('category')   # expects category id or name
        account = payload.get('account', 'cash')
        date = payload.get('date')
        if amount is None or date is None or not category_val:
            return JsonResponse({'message':'amount, date, category required'}, status=400)

        # find category by id or name
        
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
            type=payload.get('type', 'expense')  # MUST match model field name
        )
                
        # FIX: Match the keys to your JS appendRowToTable function
        return JsonResponse({
            'id': txn.id,
            'amount': float(txn.amount),
            'date': str(txn.date),
            'account': txn.account,
            'category': cat.name,  # JS looks for 'category', not 'category_name'
            'type': txn.type  
        })
    except Exception as e:
        return JsonResponse({'message': str(e)}, status=400)

# core/views.py

@require_http_methods(["POST"])
@login_required
def api_delete_transactions(request):
    try:
        payload = json.loads(request.body)
        ids = payload.get('ids', [])
        
        if not ids:
            return JsonResponse({'message': 'No IDs provided'}, status=400)

        # Filter by user to ensure people can't delete other people's data
        deleted_count, _ = Transaction.objects.filter(id__in=ids, user=request.user).delete()
        
        return JsonResponse({'message': f'Deleted {deleted_count} transactions'})
    except Exception as e:
        return JsonResponse({'message': str(e)}, status=400)
    

@require_http_methods(["DELETE"])
@login_required
def category_delete(request, pk):
    try:
        category = Category.objects.get(pk=pk)
        category.delete()
        return JsonResponse({"message": "Category deleted successfully"})
    except Category.DoesNotExist:
        return JsonResponse({"message": "Category not found"}, status=404)
    
@login_required
def transaction(request):
    # This fetches the initial data for the table when the page loads
    transactions = Transaction.objects.filter(user=request.user).order_by('-date')
    
    # Make sure the template name here matches your actual .html file name!
    return render(request, 'transaction.html', {'transactions': transactions})