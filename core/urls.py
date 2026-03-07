from django.urls import path
from . import views

urlpatterns = [
    path('',                                        views.home,                    name='home'),
    path('accounts/',                               views.accounts,                name='accounts'),
    path('transaction/',                            views.transaction,             name='transaction'),

    # Category API
    path('api/categories/',                         views.api_categories,          name='api-categories'),
    path('api/categories/<int:pk>/',                views.category_delete),

    # Transaction API
    path('api/transactions/',                       views.api_transactions,        name='api-transactions'),
    path('api/transactions/<int:pk>/edit/',         views.api_transaction_edit,    name='api-transaction-edit'),
    path('api/transactions/delete/',                views.api_delete_transactions, name='api-transactions-delete'),

    # Transfer & balances
    path('api/transfer/',                           views.api_transfer,            name='api-transfer'),
    path('api/balances/',                           views.api_balances,            name='api-balances'),

    # Summary / dashboard data
    path('api/summary/',                            views.api_summary,             name='api-summary'),
    path('api/account-summary/<str:account>/',      views.api_account_summary,     name='api-account-summary'),
]