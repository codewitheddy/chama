from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal


class ExpenseCategory(models.Model):
    """
    Admin-defined expense categories.
    At least one category must exist before an expense can be recorded.
    """
    name        = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Expense Category'
        verbose_name_plural = 'Expense Categories'

    def __str__(self):
        return self.name


class Expense(models.Model):
    """
    Records a group expense — e.g. venue hire, stationery, party, transport.

    Fund source mirrors the Loan pattern:
      - group_funds  → deducted from the available group fund balance
      - bank_account → deducted from a specific bank account (BankBalance snapshot)
      - other        → free-text description, no automatic balance deduction
    """

    FUND_SOURCE_CHOICES = [
        ('group_funds',       'Group Funds'),
        ('registration_fees', 'Registration Fee Fund'),
        ('bank_account',      'Bank Account'),
        ('other',             'Other Source'),
    ]

    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name='expenses',
        help_text='Select the expense category.',
    )
    description = models.CharField(
        max_length=300,
        help_text='What was the expense for? e.g. Venue hire, Stationery',
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    date = models.DateField()
    receipt_number = models.CharField(
        max_length=100,
        blank=True,
        help_text='Receipt or invoice reference number.',
    )
    notes = models.TextField(blank=True)

    # ── Fund source (mirrors Loan model) ─────────────────────────
    fund_source = models.CharField(
        max_length=20,
        choices=FUND_SOURCE_CHOICES,
        default='group_funds',
        help_text='Where the money was taken from.',
    )
    fund_source_bank = models.ForeignKey(
        'bank_accounts.BankAccount',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='expenses_funded',
        help_text='Set when fund_source is "bank_account".',
    )
    fund_source_label = models.CharField(
        max_length=200, blank=True,
        help_text='Free-text description when fund_source is "other".',
    )

    # ── Audit ─────────────────────────────────────────────────────
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='expenses_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.description} — KES {self.amount:,.2f} on {self.date}"

    @property
    def fund_source_description(self):
        if self.fund_source == 'bank_account' and self.fund_source_bank:
            return f"{self.fund_source_bank.bank_name} — {self.fund_source_bank.account_name}"
        if self.fund_source == 'registration_fees':
            return 'Registration Fee Fund'
        if self.fund_source == 'other' and self.fund_source_label:
            return self.fund_source_label
        return 'Group Funds'
