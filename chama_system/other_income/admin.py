from django.contrib import admin
from .models import OtherIncome


@admin.register(OtherIncome)
class OtherIncomeAdmin(admin.ModelAdmin):
    list_display = [
        'source',
        'category',
        'amount',
        'payment_method',
        'affected_account_display',
        'date',
        'reference_number',
        'is_reconciled',
    ]
    list_filter = [
        'payment_method',
        'category',
        'is_reconciled',
        'bank_account',
        'date',
    ]
    search_fields = [
        'source',
        'reference_number',
        'description',
        'reconciliation_notes',
    ]
    ordering = ['-date', '-created_at']
