from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone


class OtherIncome(models.Model):
    """
    Records external and non-member revenues for the group —
    e.g. Fixed Deposit interest, T-Bills, Money Market Fund yields,
    dividends from SACCO/company shares, grants/donations, fundraising, or asset sales.
    """

    # Category / Stream
    CATEGORY_FIXED_DEPOSIT = 'fixed_deposit'
    CATEGORY_TBILL_BOND    = 'tbill_bond'
    CATEGORY_MMF           = 'mmf'
    CATEGORY_DIVIDENDS     = 'dividends'
    CATEGORY_GRANT         = 'grant_donation'
    CATEGORY_FUNDRAISING   = 'fundraising'
    CATEGORY_BANK_INTEREST = 'bank_interest'
    CATEGORY_ASSET_SALE    = 'asset_sale'
    CATEGORY_RENTAL        = 'rental'
    CATEGORY_OTHER         = 'other'

    CATEGORY_CHOICES = [
        (CATEGORY_FIXED_DEPOSIT, 'Fixed Deposit Interest'),
        (CATEGORY_TBILL_BOND,    'Treasury Bills / Bonds Return'),
        (CATEGORY_MMF,           'Money Market Fund (MMF) Yield'),
        (CATEGORY_DIVIDENDS,     'Dividends / SACCO Shares'),
        (CATEGORY_GRANT,         'Grant / Donor Funding'),
        (CATEGORY_FUNDRAISING,   'Fundraising / Harambee'),
        (CATEGORY_BANK_INTEREST, 'Bank Operating Account Interest'),
        (CATEGORY_ASSET_SALE,    'Asset / Equipment Sale'),
        (CATEGORY_RENTAL,        'Rental / Facility Income'),
        (CATEGORY_OTHER,         'Other / Miscellaneous Income'),
    ]

    # Mode of payment
    PAYMENT_BANK_TRANSFER = 'bank_transfer'
    PAYMENT_CASH          = 'cash'
    PAYMENT_MPESA         = 'mpesa'
    PAYMENT_CHEQUE        = 'cheque'

    PAYMENT_METHOD_CHOICES = [
        (PAYMENT_BANK_TRANSFER, 'Direct Bank Transfer'),
        (PAYMENT_CASH,          'Cash (Cash in Hand)'),
        (PAYMENT_MPESA,         'M-Pesa (Mobile Wallet / Till)'),
        (PAYMENT_CHEQUE,        'Cheque Deposit'),
    ]

    source = models.CharField(
        max_length=200,
        help_text='e.g. KCB Fixed Deposit, CBK T-Bills, CIC MMF, Safaricom Dividend'
    )
    category = models.CharField(
        max_length=40,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_OTHER,
        help_text='Stream classification for auditing and reporting'
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Amount received in KES',
    )
    date = models.DateField(default=timezone.localdate)

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default=PAYMENT_CASH,
        help_text='Mode of payment: Direct Bank Transfer, Cash, M-Pesa, or Cheque',
    )

    bank_account = models.ForeignKey(
        'bank_accounts.BankAccount',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='other_incomes',
        help_text='The destination commercial bank account if paid by Direct Bank Transfer or Cheque.',
    )

    reference_number = models.CharField(
        max_length=100,
        blank=True,
        help_text='Bank transaction ref, cheque number, M-Pesa code, or official receipt number.',
    )

    receipt_attachment = models.FileField(
        upload_to='other_income/receipts/',
        blank=True,
        null=True,
        help_text='Scanned credit advice, bank statement screenshot, cheque deposit slip, or receipt.',
    )

    description = models.TextField(
        blank=True,
        help_text='Interest rates, maturity period, certificate number, or additional notes',
    )

    # Internal linkage to bank ledger if bank account was affected
    bank_balance_entry = models.ForeignKey(
        'bank_accounts.BankBalance',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='other_income_records',
        help_text='Underlying ledger entry in the bank balance statement.',
    )

    # Reconciliation tracking
    is_reconciled = models.BooleanField(
        default=False,
        help_text='Whether this transaction has been verified against the bank statement or physical cash count.',
    )
    reconciled_date = models.DateField(null=True, blank=True)
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='other_incomes_reconciled',
    )
    reconciliation_notes = models.CharField(
        max_length=255,
        blank=True,
        help_text='Statement page, line item, or voucher verification details',
    )

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='other_incomes_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Other Income'
        verbose_name_plural = 'Other Incomes'

    def __str__(self):
        return f"{self.source} ({self.get_payment_method_display()}) — KES {self.amount:,.2f} on {self.date}"

    @property
    def affected_account_display(self):
        """Human-readable name of the affected money location."""
        if self.payment_method in (self.PAYMENT_BANK_TRANSFER, self.PAYMENT_CHEQUE):
            if self.bank_account:
                acct_num = f" - {self.bank_account.account_number}" if self.bank_account.account_number else ""
                return f"{self.bank_account.bank_name}{acct_num}"
            return "Bank Account (Unassigned)"
        elif self.payment_method == self.PAYMENT_CASH:
            return "Cash in Hand (Treasurer)"
        elif self.payment_method == self.PAYMENT_MPESA:
            return "M-Pesa Wallet / Till"
        return "Unspecified"

    @property
    def affected_account_type(self):
        """Account type key for filtering or styling ('bank', 'cash', 'mpesa')."""
        if self.payment_method in (self.PAYMENT_BANK_TRANSFER, self.PAYMENT_CHEQUE):
            return "bank"
        elif self.payment_method == self.PAYMENT_CASH:
            return "cash"
        elif self.payment_method == self.PAYMENT_MPESA:
            return "mpesa"
        return "other"

    def clean(self):
        super().clean()
        if self.payment_method in (self.PAYMENT_BANK_TRANSFER, self.PAYMENT_CHEQUE):
            if not self.bank_account:
                raise ValidationError({
                    'bank_account': "Please select the destination bank account for direct bank transfers and cheques."
                })
        elif self.payment_method in (self.PAYMENT_CASH, self.PAYMENT_MPESA):
            self.bank_account = None

    def sync_bank_ledger(self):
        """
        Ensures the bank ledger reflects this direct bank deposit if paid into a bank account.
        """
        from bank_accounts.models import BankBalance
        is_bank = self.payment_method in (self.PAYMENT_BANK_TRANSFER, self.PAYMENT_CHEQUE)

        with transaction.atomic():
            if is_bank and self.bank_account:
                ref_txt = f" (Ref: {self.reference_number})" if self.reference_number else ""
                note_str = f"Other Income #{self.pk}: {self.source}{ref_txt}"

                if self.bank_balance_entry_id:
                    entry = BankBalance.objects.filter(pk=self.bank_balance_entry_id).first()
                    if entry:
                        if entry.account_id != self.bank_account_id:
                            entry.delete()
                            new_bal = self.bank_account.current_balance + self.amount
                            new_entry = BankBalance.objects.create(
                                account=self.bank_account,
                                balance=new_bal,
                                topup_amount=self.amount,
                                transaction_type=BankBalance.TYPE_TOPUP,
                                recorded_on=self.date,
                                notes=note_str,
                                recorded_by=self.recorded_by,
                            )
                            OtherIncome.objects.filter(pk=self.pk).update(bank_balance_entry=new_entry)
                            self.bank_balance_entry = new_entry
                        else:
                            diff = self.amount - entry.topup_amount
                            entry.topup_amount = self.amount
                            entry.balance = entry.balance + diff
                            entry.recorded_on = self.date
                            entry.notes = note_str
                            entry.save()
                    else:
                        new_bal = self.bank_account.current_balance + self.amount
                        new_entry = BankBalance.objects.create(
                            account=self.bank_account,
                            balance=new_bal,
                            topup_amount=self.amount,
                            transaction_type=BankBalance.TYPE_TOPUP,
                            recorded_on=self.date,
                            notes=note_str,
                            recorded_by=self.recorded_by,
                        )
                        OtherIncome.objects.filter(pk=self.pk).update(bank_balance_entry=new_entry)
                        self.bank_balance_entry = new_entry
                else:
                    new_bal = self.bank_account.current_balance + self.amount
                    new_entry = BankBalance.objects.create(
                        account=self.bank_account,
                        balance=new_bal,
                        topup_amount=self.amount,
                        transaction_type=BankBalance.TYPE_TOPUP,
                        recorded_on=self.date,
                        notes=note_str,
                        recorded_by=self.recorded_by,
                    )
                    OtherIncome.objects.filter(pk=self.pk).update(bank_balance_entry=new_entry)
                    self.bank_balance_entry = new_entry
            else:
                if self.bank_balance_entry_id:
                    entry = BankBalance.objects.filter(pk=self.bank_balance_entry_id).first()
                    OtherIncome.objects.filter(pk=self.pk).update(bank_balance_entry=None)
                    self.bank_balance_entry = None
                    if entry:
                        entry.delete()

    def delete(self, *args, **kwargs):
        if self.bank_balance_entry_id:
            from bank_accounts.models import BankBalance
            BankBalance.objects.filter(pk=self.bank_balance_entry_id).delete()
        super().delete(*args, **kwargs)
