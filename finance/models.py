from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Category(TimeStampedModel):
    INCOME = 'income'
    EXPENSE = 'expense'
    CATEGORY_TYPE_CHOICES = [
        (INCOME, 'Income'),
        (EXPENSE, 'Expense'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=10, choices=CATEGORY_TYPE_CHOICES)
    description = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ['category_type', 'name']
        unique_together = ('user', 'name', 'category_type')

    def __str__(self):
        return f'{self.name} ({self.get_category_type_display()})'


class Transaction(TimeStampedModel):
    INCOME = 'income'
    EXPENSE = 'expense'
    TRANSACTION_TYPE_CHOICES = [
        (INCOME, 'Income'),
        (EXPENSE, 'Expense'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='transactions')
    title = models.CharField(max_length=150)
    notes = models.TextField(blank=True)
    date = models.DateField(default=date.today)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)

    class Meta:
        ordering = ['-date', '-created_at']

    def clean(self):
        if self.category and self.transaction_type != self.category.category_type:
            raise ValidationError({'category': 'Category type must match the transaction type.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.title} - {self.amount}'


class Budget(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='budgets')
    month = models.DateField(help_text='Store the first day of the budget month.')
    limit_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['-month']
        unique_together = ('user', 'month')

    def clean(self):
        if self.month and self.month.day != 1:
            raise ValidationError({'month': 'Budget month must be saved as the first day of that month.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user.username} - {self.month:%B %Y}'


def create_default_categories_for_user(user):
    default_categories = {
        Category.INCOME: ['Salary', 'Freelance', 'Investments', 'Business', 'Gift'],
        Category.EXPENSE: ['Food', 'Travel', 'Bills', 'Shopping', 'Health', 'Entertainment'],
    }

    for category_type, names in default_categories.items():
        for name in names:
            Category.objects.get_or_create(
                user=user,
                name=name,
                category_type=category_type,
                defaults={'is_default': True},
            )
