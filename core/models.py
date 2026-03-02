from django.db import models
from django.contrib.auth.models import User

CATEGORY_TYPE = (
    ('income', 'Income'),
    ('expense', 'Expense'),
)

class Category(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=CATEGORY_TYPE, default='expense')

    def __str__(self):
        return self.name


class Transaction(models.Model):
    TRANSACTION_TYPE = (
        ('income', 'Income'),
        ('expense', 'Expense'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    type = models.CharField(max_length=10, choices=TRANSACTION_TYPE, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    account = models.CharField(max_length=50, default='cash')   # <-- new
    description = models.TextField(blank=True, null=True)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.user.username} - {self.type} - {self.amount}"