from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('accounts/', views.accounts, name='accounts'),
    path('transaction/', views.transaction, name='transaction'),
    path('api/categories/', views.api_categories, name='api-categories'),
    path('api/transactions/', views.api_transactions, name='api-transactions'),
    path('api/transactions/delete/', views.api_delete_transactions, name='api-transactions-delete'),
    path('api/categories/<int:pk>/', views.category_delete),
    # path('api/transfer/', views.api_transfer, name='api-transfer'),   # ← NEW
]