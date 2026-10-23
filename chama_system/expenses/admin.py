from django.contrib import admin
from .models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display  = ['name', 'is_active', 'created_at']
    list_filter   = ['is_active']
    search_fields = ['name']


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display   = ['description', 'category', 'amount', 'date', 'fund_source', 'recorded_by']
    list_filter    = ['fund_source', 'category', 'date']
    search_fields  = ['description', 'receipt_number']
    readonly_fields = ['recorded_by', 'created_at', 'updated_at']
