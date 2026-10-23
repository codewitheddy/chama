from django.contrib import admin
from .models import (
    Loan, LoanRollover, LoanProduct, NonMemberApplicant,
    LoanGuarantor, Collateral, LoanApplication, SystemSetting,
    LoanRestructure, RepaymentSchedule,
)


class LoanGuarantorInline(admin.TabularInline):
    model = LoanGuarantor
    extra = 0


class CollateralInline(admin.TabularInline):
    model = Collateral
    extra = 0


class RepaymentScheduleInline(admin.TabularInline):
    model = RepaymentSchedule
    extra = 0
    readonly_fields = [
        'installment_number', 'due_date', 'principal_amount',
        'interest_amount', 'total_installment', 'paid_amount',
        'is_paid', 'superseded_by', 'created_at'
    ]
    can_delete = False


@admin.register(NonMemberApplicant)
class NonMemberApplicantAdmin(admin.ModelAdmin):
    list_display  = ['full_name', 'phone', 'id_number', 'employer',
                     'monthly_income', 'qualification_status', 'created_at']
    list_filter   = ['qualification_status']
    search_fields = ['full_name', 'phone', 'id_number']
    readonly_fields = ['created_at', 'updated_at', 'qualified_at']
    fieldsets = (
        ('Personal Details', {
            'fields': ('full_name', 'phone', 'id_number', 'email', 'address', 'id_document'),
        }),
        ('Financial Profile', {
            'fields': ('employer', 'monthly_income', 'reason_for_loan'),
        }),
        ('Qualification', {
            'fields': ('qualification_status', 'qualification_notes', 'qualified_by', 'qualified_at'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(LoanProduct)
class LoanProductAdmin(admin.ModelAdmin):
    list_display  = ['name', 'interest_type', 'interest_frequency', 'interest_rate',
                     'duration_months', 'min_amount', 'max_amount', 'is_emergency', 'is_active']
    list_filter   = ['interest_type', 'is_emergency', 'is_active']
    search_fields = ['name']


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display  = ['__str__', 'borrower_type', 'product', 'loan_amount', 'loan_type',
                     'duration_months', 'interest_amount', 'total_payable',
                     'amount_paid', 'status', 'date_taken', 'due_date']
    list_filter   = ['status', 'loan_type', 'borrower_type', 'fund_source']
    search_fields = ['member__name', 'non_member__full_name']
    readonly_fields = ['interest_amount', 'total_payable', 'borrower_name']
    inlines = [LoanGuarantorInline, CollateralInline, RepaymentScheduleInline]


@admin.register(LoanRollover)
class LoanRolloverAdmin(admin.ModelAdmin):
    list_display  = ['loan', 'rolled_on', 'balance_before', 'new_interest', 'new_total']
    readonly_fields = ['loan', 'rolled_on', 'balance_before', 'new_interest', 'new_total']


@admin.register(LoanGuarantor)
class LoanGuarantorAdmin(admin.ModelAdmin):
    list_display  = ['loan', 'guarantor', 'amount_guaranteed', 'created_at']
    search_fields = ['loan__member__name', 'guarantor__name']


@admin.register(Collateral)
class CollateralAdmin(admin.ModelAdmin):
    list_display  = ['loan', 'description', 'estimated_value', 'created_at']
    search_fields = ['loan__member__name', 'description']


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    list_display  = ['__str__', 'member', 'loan_amount', 'duration_months', 'status', 'applied_at', 'reviewed_at']
    list_filter   = ['status']
    search_fields = ['member__name', 'reason']
    readonly_fields = ['applied_at', 'reviewed_at']


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display  = ['key', 'value', 'label', 'updated_at']
    search_fields = ['key', 'label', 'value']


@admin.register(LoanRestructure)
class LoanRestructureAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'loan', 'get_borrower', 'restructure_type',
        'status', 'requested_by', 'approved_by',
        'requested_at', 'approved_at'
    ]
    list_filter = ['status', 'restructure_type', 'requested_at']
    search_fields = [
        'loan__member__name', 'loan__non_member__full_name',
        'reason', 'rejection_reason'
    ]
    readonly_fields = [
        'requested_at', 'approved_at',
        'old_schedule_snapshot', 'new_schedule_snapshot'
    ]

    def get_borrower(self, obj):
        return obj.loan.borrower_name
    get_borrower.short_description = 'Borrower'


@admin.register(RepaymentSchedule)
class RepaymentScheduleAdmin(admin.ModelAdmin):
    list_display = [
        'loan', 'installment_number', 'due_date',
        'principal_amount', 'interest_amount', 'total_installment',
        'paid_amount', 'is_paid', 'superseded_by', 'restructure'
    ]
    list_filter = ['is_paid', 'due_date']
    search_fields = ['loan__member__name', 'loan__non_member__full_name']

