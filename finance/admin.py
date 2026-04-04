from django.contrib import admin

from .models import Budget, Category, Transaction


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'category_type', 'is_default')
    list_filter = ('category_type', 'is_default')
    search_fields = ('name', 'user__username')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'transaction_type', 'category', 'amount', 'date')
    list_filter = ('transaction_type', 'category')
    search_fields = ('title', 'user__username', 'category__name')


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('user', 'month', 'limit_amount')
    search_fields = ('user__username',)
