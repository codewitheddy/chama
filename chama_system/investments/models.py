from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
from members.models import Member


class InvestmentCategory(models.Model):
    """
    Admin-defined investment categories for grouping investment types.
    Examples: Real Estate, Stocks, Bonds, Fixed Deposits, etc.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        default='bi-briefcase',
        help_text='Bootstrap icon class (e.g., bi-building, bi-graph-up)',
    )
    color_code = models.CharField(
        max_length=7,
        default='#2563eb',
        help_text='Hex color code (e.g., #2563eb for blue)',
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0, help_text='Order in dropdown')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name_plural = 'Investment Categories'

    def __str__(self):
        return self.name


class InvestmentType(models.Model):
    """
    Admin-defined investment product templates.
    Examples: Land, Shares, Mutual Fund, T-Bills, Fixed Deposit, House, etc.
    """
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True)
    
    # Link to category
    category = models.ForeignKey(
        InvestmentCategory,
        on_delete=models.PROTECT,
        related_name='investment_types',
        help_text='Category this investment type belongs to',
    )
    
    # Optional: expected annual return rate for planning/projections
    expected_return_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Expected annual return %, e.g., 8.50 for 8.5%.',
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'name']
        verbose_name_plural = 'Investment Types'

    def __str__(self):
        return self.name


class Investment(models.Model):
    """
    Core investment transaction: when a group buys/acquires an investment.
    Tracks what was bought, when, for how much, and from what fund source.
    """
    STATUS_CHOICES = [
        ('active',    'Active'),
        ('completed', 'Completed / Liquidated'),
        ('suspended', 'Suspended'),
    ]

    FUND_SOURCE_CHOICES = [
        ('group_funds',   'Group Funds'),
        ('bank_account',  'Bank Account'),
        ('bank_transfer', 'Bank Transfer'),
        ('other',         'Other Source'),
    ]

    # What
    investment_type = models.ForeignKey(
        InvestmentType,
        on_delete=models.PROTECT,
        related_name='investments',
    )

    # How much and when
    initial_amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Initial capital invested.',
    )
    date_invested = models.DateField(default=timezone.now)
    
    # Additional units/quantity (optional)
    quantity = models.DecimalField(
        max_digits=12, decimal_places=4, default=Decimal('1.00'),
        validators=[MinValueValidator(Decimal('0.0001'))],
        help_text='Number of units/shares/plots. Defaults to 1.',
    )

    # Description / notes
    description = models.TextField(
        blank=True,
        help_text='e.g., Plot size, location, property details, certificate numbers, etc.',
    )

    # Fund source
    fund_source = models.CharField(
        max_length=20,
        choices=FUND_SOURCE_CHOICES,
        default='group_funds',
        help_text='Where the investment capital came from.',
    )
    fund_source_bank = models.ForeignKey(
        'bank_accounts.BankAccount',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='investments_funded',
        help_text='Set when fund_source is "bank_account" or "bank_transfer".',
    )
    fund_source_label = models.CharField(
        max_length=200, blank=True,
        help_text='Free-text description when fund_source is "other".',
    )

    # Payment tracking
    from utils.payment_type_mixin import PaymentTypeMixin
    payment_type = models.CharField(
        max_length=20,
        choices=[('cash', 'Cash'), ('mpesa', 'M-Pesa'), ('bank_transfer', 'Bank Transfer')],
        default='cash',
    )
    mpesa_code = models.CharField(max_length=20, blank=True)

    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
    )

    # Approval tracking for fund deduction
    funds_deducted = models.BooleanField(
        default=False,
        help_text='Funds have been deducted from the source when approved.',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='investments_approved',
        help_text='Admin user who approved and deducted funds.',
    )
    approved_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When funds were deducted.',
    )

    # Documentation
    certificate_number = models.CharField(
        max_length=100, blank=True,
        help_text='Cert of deposit, share certificate, land deed, etc.',
    )
    document = models.FileField(
        upload_to='investments/docs/',
        blank=True, null=True,
        help_text='PDF or image of certificate, deed, or proof of purchase.',
    )

    # Audit fields
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='investments_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_invested']
        verbose_name_plural = 'Investments'

    def __str__(self):
        return f"{self.investment_type.name} — KES {self.initial_amount:,.2f} on {self.date_invested}"

    @property
    def current_value(self):
        """Most recent valuation, or initial amount if no valuations yet."""
        latest = self.valuations.order_by('-valuation_date').first()
        return latest.current_value if latest else self.initial_amount

    @property
    def total_returns_received(self):
        """Sum of all returns/dividends received on this investment."""
        total = self.returns.aggregate(t=models.Sum('amount'))['t']
        return total or Decimal('0.00')

    @property
    def total_withdrawn(self):
        """Sum of all amounts withdrawn / cashed out."""
        total = self.withdrawals.aggregate(t=models.Sum('amount'))['t']
        return total or Decimal('0.00')

    @property
    def net_gain_loss(self):
        """Current value + returns - initial amount."""
        gain = self.current_value + self.total_returns_received - self.initial_amount
        return gain

    @property
    def roi_percentage(self):
        """Return on investment as a percentage."""
        if self.initial_amount == 0:
            return Decimal('0.00')
        return (self.net_gain_loss / self.initial_amount * 100).quantize(Decimal('0.01'))

    def check_fund_availability(self):
        """
        Check if sufficient funds are available from the selected source.
        Returns (is_available: bool, available_balance: Decimal, message: str)
        """
        from utils.financials import get_available_fund_balance
        from bank_accounts.models import BankAccount

        if self.fund_source == 'group_funds':
            available = get_available_fund_balance()
            is_available = self.initial_amount <= available
            return (is_available, available, f'Group fund balance: KES {available:,.2f}')

        elif self.fund_source in ('bank_account', 'bank_transfer'):
            if not self.fund_source_bank:
                if self.fund_source == 'bank_transfer':
                    return (True, Decimal('0'), 'Direct bank transfer (external source).')
                return (False, Decimal('0'), 'Bank account not selected.')
            available = self.fund_source_bank.current_balance
            is_available = self.initial_amount <= available
            return (is_available, available, f'{self.fund_source_bank.bank_name} balance: KES {available:,.2f}')

        elif self.fund_source == 'other':
            # No balance check for external funds
            return (True, Decimal('0'), 'External source (no balance check).')

        return (False, Decimal('0'), 'Unknown fund source.')


class InvestmentValuation(models.Model):
    """
    Periodic revaluation of an investment.
    Tracks how the investment value changes over time.
    """
    investment = models.ForeignKey(
        Investment,
        on_delete=models.CASCADE,
        related_name='valuations',
    )

    valuation_date = models.DateField(default=timezone.now)
    
    # Can track either per-unit value or total value
    current_value = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Total current value of this investment.',
    )
    
    # Optional: per-unit value for shares, land plots, etc.
    value_per_unit = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Price per unit/share/plot (optional).',
    )

    notes = models.TextField(
        blank=True,
        help_text='e.g., Market conditions, valuation method, appraiser name.',
    )

    valuation_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='valuations_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-valuation_date']
        verbose_name_plural = 'Investment Valuations'

    def __str__(self):
        return f"{self.investment} — KES {self.current_value:,.2f} on {self.valuation_date}"

    @property
    def gain_loss_from_purchase(self):
        """Difference between current valuation and initial purchase price."""
        gain = self.current_value - self.investment.initial_amount
        return gain

    @property
    def gain_loss_percentage(self):
        """Percentage change from initial investment."""
        if self.investment.initial_amount == 0:
            return Decimal('0.00')
        pct = (self.gain_loss_from_purchase / self.investment.initial_amount * 100).quantize(Decimal('0.01'))
        return pct


class InvestmentReturn(models.Model):
    """
    Dividends, interest, or other income/returns paid FROM an investment.
    E.g., annual dividend from shares, interest from fixed deposit, rental income.
    """
    investment = models.ForeignKey(
        Investment,
        on_delete=models.CASCADE,
        related_name='returns',
    )

    RETURN_TYPE_CHOICES = [
        ('dividend',       'Dividend'),
        ('interest',       'Interest'),
        ('rental',         'Rental Income'),
        ('bonus',          'Bonus/Capital Gain'),
        ('other',          'Other Return'),
    ]

    return_type = models.CharField(max_length=20, choices=RETURN_TYPE_CHOICES)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    return_date = models.DateField(default=timezone.now)
    
    # Payment method
    payment_type = models.CharField(
        max_length=20,
        choices=[('cash', 'Cash'), ('mpesa', 'M-Pesa'), ('bank_transfer', 'Bank Transfer')],
        default='cash',
    )
    mpesa_code = models.CharField(max_length=20, blank=True)
    bank_account = models.ForeignKey(
        'bank_accounts.BankAccount',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='investment_returns_received',
        help_text='Set when payment_type is "bank_transfer".',
    )

    # Description
    description = models.TextField(blank=True)

    # Audit
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='investment_returns_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-return_date']
        verbose_name_plural = 'Investment Returns'

    def __str__(self):
        return f"{self.get_return_type_display()} — {self.investment} — KES {self.amount:,.2f}"


class InvestmentWithdrawal(models.Model):
    """
    Partial or full withdrawal/liquidation of an investment.
    E.g., selling shares, withdrawing from fixed deposit, selling a plot.
    """
    investment = models.ForeignKey(
        Investment,
        on_delete=models.CASCADE,
        related_name='withdrawals',
    )

    WITHDRAWAL_TYPE_CHOICES = [
        ('partial',  'Partial Withdrawal'),
        ('full',     'Full Liquidation'),
    ]

    withdrawal_type = models.CharField(max_length=20, choices=WITHDRAWAL_TYPE_CHOICES)
    
    # How much
    quantity_withdrawn = models.DecimalField(
        max_digits=12, decimal_places=4,
        validators=[MinValueValidator(Decimal('0.0001'))],
        help_text='Number of units/shares withdrawn.',
    )
    amount_received = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Cash received from this withdrawal/sale.',
    )

    # When and how
    withdrawal_date = models.DateField(default=timezone.now)
    payment_type = models.CharField(
        max_length=20,
        choices=[('cash', 'Cash'), ('mpesa', 'M-Pesa'), ('bank_transfer', 'Bank Transfer')],
        default='cash',
    )
    mpesa_code = models.CharField(max_length=20, blank=True)
    bank_account = models.ForeignKey(
        'bank_accounts.BankAccount',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='investment_withdrawals_received',
        help_text='Set when payment_type is "bank_transfer".',
    )

    # Description
    buyer_name = models.CharField(
        max_length=200, blank=True,
        help_text='Who bought it, name of buyer/investor.',
    )
    notes = models.TextField(blank=True)

    # Audit
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='investment_withdrawals_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-withdrawal_date']
        verbose_name_plural = 'Investment Withdrawals'

    def __str__(self):
        return f"{self.get_withdrawal_type_display()} — {self.investment} — KES {self.amount_received:,.2f}"

    @property
    def gain_loss(self):
        """Amount gained/lost on this sale."""
        cost_basis = (self.quantity_withdrawn / self.investment.quantity * self.investment.initial_amount).quantize(Decimal('0.01'))
        gain = self.amount_received - cost_basis
        return gain
