from django.contrib import admin
from .models import Member, MemberExit, RegistrationFeePayment, RegistrationFeeRate


@admin.register(RegistrationFeeRate)
class RegistrationFeeRateAdmin(admin.ModelAdmin):
    list_display = ['amount', 'effective_date', 'created_at']
    list_filter = ['effective_date']
    ordering = ['-effective_date']
    
    fieldsets = (
        ('Fee Rate', {
            'fields': ('amount', 'effective_date')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('System', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'registration_fee_paid', 'date_joined', 'is_active']
    search_fields = ['name', 'phone']
    list_filter = ['date_joined', 'is_active']


@admin.register(MemberExit)
class MemberExitAdmin(admin.ModelAdmin):
    list_display = ['member', 'exit_date', 'contributions_returned',
                    'profit_share_paid', 'outstanding_loans_deducted', 'net_payout']
    search_fields = ['member__name']
    readonly_fields = ['recorded_by', 'created_at']


@admin.register(RegistrationFeePayment)
class RegistrationFeePaymentAdmin(admin.ModelAdmin):
    list_display = ['member', 'amount', 'payment_date', 'payment_method', 'receipt_number']
    search_fields = ['member__name', 'receipt_number']
    list_filter = ['payment_date', 'payment_method']
    readonly_fields = ['created_at', 'updated_at', 'recorded_by']
    
    fieldsets = (
        ('Member & Amount', {
            'fields': ('member', 'amount')
        }),
        ('Payment Details', {
            'fields': ('payment_date', 'payment_method', 'receipt_number', 'notes')
        }),
        ('System', {
            'fields': ('recorded_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # New record
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)
