from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal


class BankAccount(models.Model):
    """A bank account held by the group."""
    FUND_TYPE_GENERAL      = 'general'
    FUND_TYPE_WELFARE      = 'welfare'
    FUND_TYPE_REGISTRATION = 'registration'

    FUND_TYPE_CHOICES = [
        (FUND_TYPE_GENERAL,      'General / Lending Fund'),
        (FUND_TYPE_WELFARE,      'Welfare Fund'),
        (FUND_TYPE_REGISTRATION, 'Registration Fee Fund'),
    ]

    bank_name      = models.CharField(max_length=200, help_text='e.g. KCB, Equity Bank')
    account_name   = models.CharField(max_length=200, help_text='e.g. Finance Wise Chama Account')
    account_number = models.CharField(max_length=50, blank=True)
    branch         = models.CharField(max_length=200, blank=True)
    fund_type      = models.CharField(
        max_length=20,
        choices=FUND_TYPE_CHOICES,
        default=FUND_TYPE_GENERAL,
        help_text='Fund this account belongs to: General Chama/Lending, Welfare, or Registration Fee Fund.',
    )
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['bank_name', 'account_name']

    def __str__(self):
        fund_label = f" [{self.get_fund_type_display()}]" if self.fund_type != self.FUND_TYPE_GENERAL else ""
        return f"{self.bank_name} — {self.account_name}{fund_label}"

    @property
    def is_welfare(self):
        return self.fund_type == self.FUND_TYPE_WELFARE

    @property
    def is_general(self):
        return self.fund_type == self.FUND_TYPE_GENERAL

    @property
    def is_registration(self):
        return self.fund_type == self.FUND_TYPE_REGISTRATION

    @property
    def current_balance(self):
        """Most recently recorded balance snapshot."""
        if not self.pk:
            return Decimal('0.00')
        latest = self.balances.first()
        return latest.balance if latest else Decimal('0.00')

    @property
    def last_updated(self):
        if not self.pk:
            return None
        latest = self.balances.first()
        return latest.recorded_on if latest else None

    @property
    def opening_balance(self):
        """The very first balance snapshot recorded for this account."""
        if not self.pk:
            return Decimal('0.00')
        first = self.balances.order_by('recorded_on', 'created_at').first()
        return first.balance if first else Decimal('0.00')

    @property
    def total_topups(self):
        if not self.pk:
            return Decimal('0.00')
        from django.db.models import Sum
        return (
            self.balances.filter(transaction_type='topup')
            .aggregate(t=Sum('topup_amount'))['t'] or Decimal('0.00')
        )


class BankBalance(models.Model):
    """
    Ledger entry for a bank account.

    Each row stores the resulting balance after the transaction, plus
    metadata about what caused the change.

    transaction_type:
      opening    — initial balance when account is first set up
      topup      — money deposited into the account
      deduction  — money withdrawn (loans, expenses, etc.)
      adjustment — manual admin correction
      snapshot   — legacy: treasurer manually recorded a point-in-time balance
    """

    TYPE_OPENING    = 'opening'
    TYPE_TOPUP      = 'topup'
    TYPE_DEDUCTION  = 'deduction'
    TYPE_ADJUSTMENT = 'adjustment'
    TYPE_SNAPSHOT   = 'snapshot'

    TRANSACTION_TYPE_CHOICES = [
        (TYPE_OPENING,    'Opening Balance'),
        (TYPE_TOPUP,      'Top-Up / Deposit'),
        (TYPE_DEDUCTION,  'Deduction / Withdrawal'),
        (TYPE_ADJUSTMENT, 'Adjustment'),
        (TYPE_SNAPSHOT,   'Manual Snapshot'),
    ]

    account = models.ForeignKey(
        BankAccount, on_delete=models.CASCADE, related_name='balances',
    )
    # Resulting balance after this entry
    balance = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    # The amount of the top-up / deduction (0 for snapshots)
    topup_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Amount added or deducted in this transaction.',
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPE_CHOICES,
        default=TYPE_SNAPSHOT,
    )
    recorded_on = models.DateField()
    notes       = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='bank_balance_entries',
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recorded_on', '-created_at']

    def __str__(self):
        return (
            f"{self.account.bank_name} | {self.get_transaction_type_display()} | "
            f"KES {self.balance:,.2f} on {self.recorded_on}"
        )

    @property
    def is_credit(self):
        return self.transaction_type in (
            self.TYPE_OPENING, self.TYPE_TOPUP, self.TYPE_ADJUSTMENT
        )

    @property
    def is_debit(self):
        return self.transaction_type == self.TYPE_DEDUCTION
