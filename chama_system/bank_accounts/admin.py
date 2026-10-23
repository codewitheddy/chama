from django.contrib import admin
from .models import BankAccount, BankBalance


class BankBalanceInline(admin.TabularInline):
    model  = BankBalance
    extra  = 0
    fields = ['balance', 'recorded_on', 'notes']
    ordering = ['-recorded_on']


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display  = ['bank_name', 'account_name', 'account_number', 'branch', 'is_active']
    list_filter   = ['is_active', 'bank_name']
    search_fields = ['bank_name', 'account_name', 'account_number']
    inlines       = [BankBalanceInline]


@admin.register(BankBalance)
class BankBalanceAdmin(admin.ModelAdmin):
    list_display  = ['account', 'balance', 'recorded_on']
    list_filter   = ['account']
    ordering      = ['-recorded_on']
