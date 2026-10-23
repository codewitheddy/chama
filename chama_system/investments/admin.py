from django.contrib import admin
from .models import InvestmentCategory, InvestmentType, Investment, InvestmentValuation, InvestmentReturn, InvestmentWithdrawal
from django.utils import timezone


class InvestmentTypeInline(admin.TabularInline):
    """Inline admin for investment types within a category."""
    model = InvestmentType
    extra = 1
    fields = ['name', 'expected_return_rate', 'is_active']


@admin.register(InvestmentCategory)
class InvestmentCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon', 'color_code', 'is_active', 'display_order', 'type_count']
    list_filter = ['is_active']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [InvestmentTypeInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description')
        }),
        ('Display Settings', {
            'fields': ('icon', 'color_code', 'display_order', 'is_active'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ['display_order', 'name']

    def type_count(self, obj):
        return obj.investment_types.count()
    type_count.short_description = 'Investment Types'


class InvestmentValuationInline(admin.TabularInline):
    """Inline admin for investment valuations."""
    model = InvestmentValuation
    extra = 1
    fields = ['valuation_date', 'current_value', 'value_per_unit', 'notes']
    ordering = ['-valuation_date']


class InvestmentReturnInline(admin.TabularInline):
    """Inline admin for investment returns."""
    model = InvestmentReturn
    extra = 1
    fields = ['return_date', 'return_type', 'amount', 'payment_type']
    ordering = ['-return_date']


class InvestmentWithdrawalInline(admin.TabularInline):
    """Inline admin for investment withdrawals."""
    model = InvestmentWithdrawal
    extra = 1
    fields = ['withdrawal_date', 'withdrawal_type', 'quantity_withdrawn', 'amount_received']
    ordering = ['-withdrawal_date']


@admin.register(InvestmentType)
class InvestmentTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'expected_return_rate', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'description']
    fieldsets = (
        ('Basics', {'fields': ('name', 'description')}),
        ('Category & Returns', {'fields': ('category', 'expected_return_rate')}),
        ('Status', {'fields': ('is_active',)}),
    )


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = [
        'investment_type',
        'initial_amount',
        'current_value_display',
        'date_invested',
        'status',
        'approval_status_display',
        'recorded_by',
    ]
    list_filter = ['status', 'investment_type', 'date_invested', 'fund_source', 'funds_deducted']
    search_fields = ['investment_type__name', 'description', 'certificate_number']
    readonly_fields = [
        'created_at', 'updated_at', 'recorded_by', 
        'current_value_display', 'total_returns_display', 
        'net_gain_loss_display', 'roi_display',
        'funds_deducted', 'approved_by', 'approved_at'
    ]
    inlines = [InvestmentValuationInline, InvestmentReturnInline, InvestmentWithdrawalInline]
    actions = [
        'approve_investments',
        'mark_as_active',
        'mark_as_completed',
        'mark_as_suspended',
        'export_as_csv',
        'reset_approval_status',
    ]
    
    fieldsets = (
        ('Investment Details', {
            'fields': ('investment_type', 'initial_amount', 'quantity', 'date_invested')
        }),
        ('Fund Source', {
            'fields': ('fund_source', 'fund_source_bank', 'fund_source_label')
        }),
        ('Payment & Documentation', {
            'fields': ('payment_type', 'mpesa_code', 'certificate_number', 'document')
        }),
        ('Description', {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
        ('Performance Summary', {
            'fields': ('current_value_display', 'total_returns_display', 'net_gain_loss_display', 'roi_display'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Approval & Fund Deduction', {
            'fields': ('funds_deducted', 'approved_by', 'approved_at'),
            'description': 'Track approval status and fund deduction for this investment.'
        }),
        ('Audit', {
            'fields': ('recorded_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ['-date_invested']

    def current_value_display(self, obj):
        return f"KES {obj.current_value:,.2f}"
    current_value_display.short_description = 'Current Value'

    def total_returns_display(self, obj):
        return f"KES {obj.total_returns_received:,.2f}"
    total_returns_display.short_description = 'Total Returns'

    def net_gain_loss_display(self, obj):
        gain = obj.net_gain_loss
        color = 'green' if gain >= 0 else 'red'
        return f'<span style="color: {color};">KES {gain:,.2f}</span>'
    net_gain_loss_display.short_description = 'Net Gain/Loss'
    net_gain_loss_display.allow_tags = True

    def roi_display(self, obj):
        roi = obj.roi_percentage
        color = 'green' if roi >= 0 else 'red'
        return f'<span style="color: {color};">{roi}%</span>'
    roi_display.short_description = 'ROI %'
    roi_display.allow_tags = True

    def approval_status_display(self, obj):
        """Display approval status in list view."""
        if obj.funds_deducted:
            approved_by = obj.approved_by.username if obj.approved_by else 'Unknown'
            return f'✓ Approved by {approved_by} on {obj.approved_at.strftime("%Y-%m-%d")}'
        else:
            return '✗ Not Approved'
    approval_status_display.short_description = 'Approval Status'

    def approve_investments(self, request, queryset):
        """Admin action to approve selected investments and deduct funds."""
        from django.db import transaction
        from django.contrib import messages
        
        approved_count = 0
        failed_investments = []
        
        for investment in queryset:
            if investment.funds_deducted:
                failed_investments.append(f"{investment.investment_type.name} (already approved)")
                continue
            
            try:
                # Check fund availability
                is_available, balance, msg = investment.check_fund_availability()
                
                if not is_available:
                    failed_investments.append(f"{investment.investment_type.name} ({msg})")
                    continue
                
                # Approve and deduct funds
                with transaction.atomic():
                    from bank_accounts.models import BankBalance
                    from expenses.models import Expense, ExpenseCategory

                    if investment.fund_source == 'group_funds':
                        # Deduct from group funds via Expense record
                        inv_category, _ = ExpenseCategory.objects.get_or_create(
                            name='Investment',
                            defaults={'description': 'Funds allocated to group investments.'},
                        )
                        Expense.objects.create(
                            category=inv_category,
                            description=(
                                f'Investment: {investment.investment_type.name} '
                                f'(#{investment.pk})'
                            ),
                            amount=investment.initial_amount,
                            date=investment.date_invested or timezone.now().date(),
                            fund_source='group_funds',
                            notes=(
                                f'Auto-created on bulk approval of investment #{investment.pk}. '
                                f'Approved by {request.user.username}.'
                            ),
                            recorded_by=request.user,
                        )

                    elif investment.fund_source == 'bank_account' and investment.fund_source_bank:
                        # Deduct from bank account via BankBalance ledger entry
                        bank = investment.fund_source_bank
                        current_balance = bank.current_balance
                        BankBalance.objects.create(
                            account=bank,
                            balance=current_balance - investment.initial_amount,
                            transaction_type=BankBalance.TYPE_DEDUCTION,
                            topup_amount=investment.initial_amount,
                            recorded_on=investment.date_invested,
                            recorded_by=request.user,
                        )
                    
                    # Mark as approved
                    investment.funds_deducted = True
                    investment.approved_by = request.user
                    investment.approved_at = timezone.now()
                    investment.save(update_fields=['funds_deducted', 'approved_by', 'approved_at'])
                    
                    approved_count += 1
            
            except Exception as e:
                failed_investments.append(f"{investment.investment_type.name} (Error: {str(e)})")
        
        # Show messages
        if approved_count > 0:
            messages.success(request, f'{approved_count} investment(s) approved and funds deducted.')
        
        if failed_investments:
            messages.warning(request, f'Failed to approve {len(failed_investments)} investment(s): {", ".join(failed_investments)}')
    
    approve_investments.short_description = 'Approve & Deduct Funds'

    def mark_as_active(self, request, queryset):
        """Bulk action to mark selected investments as active."""
        from django.contrib import messages
        
        updated = queryset.update(status='active')
        messages.success(request, f'{updated} investment(s) marked as active.')
    
    mark_as_active.short_description = 'Mark as Active'

    def mark_as_completed(self, request, queryset):
        """Bulk action to mark selected investments as completed."""
        from django.contrib import messages
        
        updated = queryset.update(status='completed')
        messages.success(request, f'{updated} investment(s) marked as completed.')
    
    mark_as_completed.short_description = 'Mark as Completed'

    def mark_as_suspended(self, request, queryset):
        """Bulk action to mark selected investments as suspended."""
        from django.contrib import messages
        
        updated = queryset.update(status='suspended')
        messages.success(request, f'{updated} investment(s) marked as suspended.')
    
    mark_as_suspended.short_description = 'Mark as Suspended'

    def reset_approval_status(self, request, queryset):
        """Bulk action to reset approval status (e.g., for re-evaluation)."""
        from django.contrib import messages
        
        # Only reset unapproved investments to prevent data loss
        queryset_unapproved = queryset.filter(funds_deducted=False)
        
        if queryset_unapproved.count() == 0:
            messages.warning(request, 'No unapproved investments selected. Skipped.')
            return
        
        updated = queryset_unapproved.update(
            approved_by=None,
            approved_at=None,
        )
        messages.success(request, f'{updated} investment(s) approval status reset.')
        
        # Warn about approved investments
        approved_count = queryset.exclude(funds_deducted=False).count()
        if approved_count > 0:
            messages.warning(request, f'{approved_count} approved investment(s) were skipped to prevent data loss.')
    
    reset_approval_status.short_description = 'Reset Approval Status'

    def export_as_csv(self, request, queryset):
        """Bulk action to export selected investments as CSV."""
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="investments_export.csv"'
        
        writer = csv.writer(response)
        
        # Header row
        writer.writerow([
            'Investment Type',
            'Category',
            'Initial Amount',
            'Current Value',
            'Total Returns',
            'Net Gain/Loss',
            'ROI %',
            'Date Invested',
            'Status',
            'Fund Source',
            'Approved',
            'Approved By',
            'Approved At',
            'Recorded By',
            'Created At',
        ])
        
        # Data rows
        for investment in queryset:
            writer.writerow([
                investment.investment_type.name,
                investment.investment_type.category.name,
                f"{investment.initial_amount:,.2f}",
                f"{investment.current_value:,.2f}",
                f"{investment.total_returns_received:,.2f}",
                f"{investment.net_gain_loss:,.2f}",
                f"{investment.roi_percentage}",
                investment.date_invested,
                investment.get_status_display(),
                investment.get_fund_source_display(),
                'Yes' if investment.funds_deducted else 'No',
                investment.approved_by.username if investment.approved_by else '',
                investment.approved_at.strftime('%Y-%m-%d %H:%M') if investment.approved_at else '',
                investment.recorded_by.username if investment.recorded_by else '',
                investment.created_at.strftime('%Y-%m-%d %H:%M'),
            ])
        
        return response
    
    export_as_csv.short_description = 'Export to CSV'

    def save_model(self, request, obj, form, change):
        if not change:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(InvestmentValuation)
class InvestmentValuationAdmin(admin.ModelAdmin):
    list_display = ['investment', 'valuation_date', 'current_value', 'value_per_unit', 'gain_loss_percentage']
    list_filter = ['valuation_date', 'investment__investment_type']
    search_fields = ['investment__investment_type__name', 'notes']
    readonly_fields = ['created_at', 'gain_loss_from_purchase', 'gain_loss_percentage']
    
    fieldsets = (
        ('Valuation', {
            'fields': ('investment', 'valuation_date', 'current_value', 'value_per_unit')
        }),
        ('Performance', {
            'fields': ('gain_loss_from_purchase', 'gain_loss_percentage'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('valuation_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ['-valuation_date']


@admin.register(InvestmentReturn)
class InvestmentReturnAdmin(admin.ModelAdmin):
    list_display = ['investment', 'return_type', 'amount', 'return_date', 'payment_type']
    list_filter = ['return_type', 'return_date', 'payment_type']
    search_fields = ['investment__investment_type__name', 'description']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Return Details', {
            'fields': ('investment', 'return_type', 'amount', 'return_date')
        }),
        ('Payment Method', {
            'fields': ('payment_type', 'mpesa_code', 'bank_account'),
            'classes': ('collapse',)
        }),
        ('Description', {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('recorded_by', 'created_at'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ['-return_date']


@admin.register(InvestmentWithdrawal)
class InvestmentWithdrawalAdmin(admin.ModelAdmin):
    list_display = ['investment', 'withdrawal_type', 'quantity_withdrawn', 'amount_received', 'withdrawal_date']
    list_filter = ['withdrawal_type', 'withdrawal_date', 'payment_type']
    search_fields = ['investment__investment_type__name', 'buyer_name', 'notes']
    readonly_fields = ['created_at', 'updated_at', 'gain_loss']
    
    fieldsets = (
        ('Withdrawal Details', {
            'fields': ('investment', 'withdrawal_type', 'quantity_withdrawn', 'amount_received', 'withdrawal_date')
        }),
        ('Buyer Information', {
            'fields': ('buyer_name',),
            'classes': ('collapse',)
        }),
        ('Payment Method', {
            'fields': ('payment_type', 'mpesa_code', 'bank_account'),
            'classes': ('collapse',)
        }),
        ('Performance', {
            'fields': ('gain_loss',),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('recorded_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    ordering = ['-withdrawal_date']
