from django.contrib import admin
from .models import Loan, LoanRollover


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ['member', 'loan_amount', 'duration_months', 'interest_amount',
                    'total_payable', 'amount_paid', 'status', 'rollover_count', 'date_taken', 'due_date']
    list_filter = ['status']
    search_fields = ['member__name']
    readonly_fields = ['interest_amount', 'total_payable']


@admin.register(LoanRollover)
class LoanRolloverAdmin(admin.ModelAdmin):
    list_display = ['loan', 'rolled_on', 'balance_before', 'new_interest', 'new_total']
    readonly_fields = ['loan', 'rolled_on', 'balance_before', 'new_interest', 'new_total']
