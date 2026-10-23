from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone


class MoneyAccount(models.Model):
    """
    Represents a monetary location/wallet in the Table Banking group:
      - cash: Physical Cash in Hand held by the Treasurer
      - mpesa: M-Pesa Paybill / Till / Mobile Wallet
      - bank: Commercial Bank Account (links to bank_accounts.BankAccount)
      - investment: Group Investment Portfolio / Capital
    """
    TYPE_CASH = 'cash'
    TYPE_MPESA = 'mpesa'
    TYPE_BANK = 'bank'
    TYPE_INVESTMENT = 'investment'

    ACCOUNT_TYPE_CHOICES = [
        (TYPE_CASH, 'Cash in Hand (Treasurer)'),
        (TYPE_MPESA, 'M-Pesa Wallet / Till / Paybill'),
        (TYPE_BANK, 'Bank Account'),
        (TYPE_INVESTMENT, 'Investments Portfolio'),
    ]

    name = models.CharField(max_length=150, help_text="Account name, e.g., 'Treasurer Cash in Hand', 'KCB Chama Account'")
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    bank_account = models.ForeignKey(
        'bank_accounts.BankAccount',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='linked_money_accounts',
        help_text="Link to specific bank account if type is Bank Account."
    )
    account_number = models.CharField(max_length=60, blank=True, help_text="Bank account number or M-Pesa Till/Paybill number")
    opening_balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Opening balance when account tracking was started."
    )
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['account_type', 'name']
        verbose_name = 'Money Account'
        verbose_name_plural = 'Money Accounts'

    def __str__(self):
        return f"{self.name} ({self.get_account_type_display()})"

    @classmethod
    def get_or_create_default_cash(cls):
        """Ensure default Cash in Hand account exists."""
        acc, _ = cls.objects.get_or_create(
            account_type=cls.TYPE_CASH,
            name='Cash in Hand (Treasurer)',
            defaults={'description': 'Physical cash held by the group treasurer.'}
        )
        return acc

    @classmethod
    def get_or_create_default_mpesa(cls):
        """Ensure default M-Pesa Wallet account exists."""
        acc, _ = cls.objects.get_or_create(
            account_type=cls.TYPE_MPESA,
            name='M-Pesa Wallet',
            defaults={'description': 'M-Pesa till, paybill, or treasurer mobile wallet.'}
        )
        return acc

    @classmethod
    def get_or_create_default_investments(cls):
        """Ensure default Investments account exists."""
        acc, _ = cls.objects.get_or_create(
            account_type=cls.TYPE_INVESTMENT,
            name='Investments Portfolio',
            defaults={'description': 'Group invested assets and capital.'}
        )
        return acc

    @classmethod
    def sync_bank_accounts(cls):
        """Sync all active General BankAccount records into MoneyAccount."""
        from bank_accounts.models import BankAccount
        # Deactivate any MoneyAccount linked to non-general bank accounts (e.g. Welfare)
        cls.objects.filter(bank_account__fund_type__in=[BankAccount.FUND_TYPE_WELFARE, BankAccount.FUND_TYPE_REGISTRATION]).update(is_active=False)
        for b in BankAccount.objects.filter(is_active=True, fund_type=BankAccount.FUND_TYPE_GENERAL):
            cls.objects.get_or_create(
                bank_account=b,
                defaults={
                    'name': f"{b.bank_name} - {b.account_name}",
                    'account_type': cls.TYPE_BANK,
                    'account_number': b.account_number,
                    'opening_balance': b.opening_balance,
                    'description': f"Branch: {b.branch}" if b.branch else ''
                }
            )


class MoneyTransfer(models.Model):
    """
    Double-entry transfer record moving money between accounts.
    Never counted as income or expense — only redistributes money across locations.
    """
    TYPE_CASH_TO_BANK = 'cash_to_bank'
    TYPE_BANK_TO_CASH = 'bank_to_cash'
    TYPE_MPESA_TO_CASH = 'mpesa_to_cash'
    TYPE_MPESA_TO_BANK = 'mpesa_to_bank'
    TYPE_CASH_TO_MPESA = 'cash_to_mpesa'
    TYPE_BANK_TO_MPESA = 'bank_to_mpesa'
    TYPE_TO_INVESTMENT = 'to_investment'
    TYPE_FROM_INVESTMENT = 'from_investment'
    TYPE_OTHER = 'other_transfer'
    TYPE_REVERSAL = 'reversal'

    TRANSFER_TYPE_CHOICES = [
        (TYPE_CASH_TO_BANK, 'Banking Cash (Cash in Hand → Bank)'),
        (TYPE_BANK_TO_CASH, 'Bank Withdrawal (Bank → Cash in Hand)'),
        (TYPE_MPESA_TO_CASH, 'M-Pesa Withdrawal to Cash (M-Pesa → Cash)'),
        (TYPE_MPESA_TO_BANK, 'M-Pesa to Bank Transfer (M-Pesa → Bank)'),
        (TYPE_CASH_TO_MPESA, 'Cash to M-Pesa Deposit (Cash → M-Pesa)'),
        (TYPE_BANK_TO_MPESA, 'Bank to M-Pesa Transfer (Bank → M-Pesa)'),
        (TYPE_TO_INVESTMENT, 'Invest Capital (Cash/Bank/M-Pesa → Investment)'),
        (TYPE_FROM_INVESTMENT, 'Investment Matures/Sold (Investment → Bank/Cash)'),
        (TYPE_OTHER, 'Internal Account Transfer'),
        (TYPE_REVERSAL, 'Reversal Entry'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_REVERSED = 'reversed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending Second Approval'),
        (STATUS_APPROVED, 'Approved / Completed'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_REVERSED, 'Reversed'),
    ]

    from_account = models.ForeignKey(
        MoneyAccount,
        on_delete=models.PROTECT,
        related_name='outgoing_transfers',
        help_text="Source account where funds are deducted."
    )
    to_account = models.ForeignKey(
        MoneyAccount,
        on_delete=models.PROTECT,
        related_name='incoming_transfers',
        help_text="Destination account where funds are deposited."
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Amount in KES to transfer."
    )
    transfer_date = models.DateField(default=timezone.now)
    transfer_type = models.CharField(max_length=30, choices=TRANSFER_TYPE_CHOICES, default=TYPE_CASH_TO_BANK)
    reference = models.CharField(
        max_length=100, blank=True,
        help_text="Deposit slip number, M-Pesa transaction code, or bank reference."
    )
    deposited_by = models.CharField(
        max_length=150, blank=True,
        help_text="Person who banked the cash or executed the physical transaction."
    )
    notes = models.TextField(blank=True, help_text="Purpose, details, or notes.")
    slip_attachment = models.FileField(
        upload_to='money_movement/slips/', blank=True, null=True,
        help_text="Scanned deposit slip, bank receipt, or M-Pesa screenshot."
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_APPROVED)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='transfers_recorded',
        help_text="Treasurer or officer who initiated this transfer."
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    # Dual approval workflow
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='transfers_approved',
        help_text="Second officer (Chairperson, Secretary, or Admin) who verified and approved."
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    # Immutability & Reversal Tracking
    is_reversal = models.BooleanField(default=False)
    reversal_of = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reversals',
        help_text="Original transfer being reversed if this is a reversal entry."
    )
    reversal_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-transfer_date', '-recorded_at']
        verbose_name = 'Money Movement Transfer'
        verbose_name_plural = 'Money Movement Transfers'

    def __str__(self):
        return f"{self.get_transfer_type_display()} — KES {self.amount:,.2f} on {self.transfer_date} ({self.get_status_display()})"

    def clean(self):
        if self.from_account_id and self.to_account_id and self.from_account_id == self.to_account_id:
            raise ValidationError("Source and destination accounts cannot be the same account.")
        if self.amount is not None and self.amount <= Decimal('0.00'):
            raise ValidationError("Transfer amount must be greater than zero.")

    def save(self, *args, **kwargs):
        # Enforce immutability once approved or reversed
        if self.pk:
            original = MoneyTransfer.objects.get(pk=self.pk)
            if original.status in [self.STATUS_APPROVED, self.STATUS_REVERSED]:
                # Disallow modifying financial core attributes directly
                if (original.amount != self.amount or
                    original.from_account_id != self.from_account_id or
                    original.to_account_id != self.to_account_id or
                    original.transfer_type != self.transfer_type):
                    raise ValidationError("Completed transfers are immutable. You must post a reversal entry to correct this.")
        super().save(*args, **kwargs)

    def approve(self, user):
        """Approve and execute a pending transfer."""
        if self.status != self.STATUS_PENDING:
            raise ValidationError("Only pending transfers can be approved.")
        with transaction.atomic():
            self.status = self.STATUS_APPROVED
            self.approved_by = user
            self.approved_at = timezone.now()
            self.save(update_fields=['status', 'approved_by', 'approved_at'])
            # If moving to/from bank, update bank ledger snapshot
            self._sync_with_bank_ledger()

    def reject(self, user, reason):
        """Reject a pending transfer with a reason."""
        if self.status != self.STATUS_PENDING:
            raise ValidationError("Only pending transfers can be rejected.")
        self.status = self.STATUS_REJECTED
        self.approved_by = user
        self.approved_at = timezone.now()
        self.rejection_reason = reason
        self.save(update_fields=['status', 'approved_by', 'approved_at', 'rejection_reason'])

    def create_reversal(self, user, reason):
        """
        Create a reversal entry for this completed transfer.
        Both entries remain in audit trail with immutable linkage.
        """
        if self.status != self.STATUS_APPROVED:
            raise ValidationError("Only approved/completed transfers can be reversed.")
        if self.reversals.filter(status=self.STATUS_APPROVED).exists():
            raise ValidationError("This transfer has already been reversed.")

        with transaction.atomic():
            reversal = MoneyTransfer.objects.create(
                from_account=self.to_account,
                to_account=self.from_account,
                amount=self.amount,
                transfer_date=timezone.localdate(),
                transfer_type=self.TYPE_REVERSAL,
                reference=f"REV-{self.reference}" if self.reference else f"REV-{self.pk}",
                deposited_by=f"Reversal by {user.get_full_name() or user.username}",
                notes=f"Reversal of Transfer #{self.pk}. Reason: {reason}",
                status=self.STATUS_APPROVED,
                recorded_by=user,
                approved_by=user,
                approved_at=timezone.now(),
                is_reversal=True,
                reversal_of=self,
                reversal_reason=reason
            )
            self.status = self.STATUS_REVERSED
            self.reversal_reason = reason
            self.save(update_fields=['status', 'reversal_reason'])
            reversal._sync_with_bank_ledger()
            return reversal

    def _sync_with_bank_ledger(self):
        """Sync transfer with BankBalance ledger if a bank account is involved."""
        from bank_accounts.models import BankBalance
        # If destination is a Bank Account, add a topup record
        if self.to_account.bank_account:
            bank = self.to_account.bank_account
            new_balance = bank.current_balance + self.amount
            BankBalance.objects.create(
                account=bank,
                balance=new_balance,
                topup_amount=self.amount,
                transaction_type=BankBalance.TYPE_TOPUP,
                recorded_on=self.transfer_date,
                notes=f"Transfer #{self.pk}: {self.get_transfer_type_display()} Ref: {self.reference}",
                recorded_by=self.recorded_by
            )
        # If source is a Bank Account, add a deduction record
        if self.from_account.bank_account:
            bank = self.from_account.bank_account
            new_balance = max(bank.current_balance - self.amount, Decimal('0.00'))
            BankBalance.objects.create(
                account=bank,
                balance=new_balance,
                topup_amount=self.amount,
                transaction_type=BankBalance.TYPE_DEDUCTION,
                recorded_on=self.transfer_date,
                notes=f"Transfer #{self.pk}: {self.get_transfer_type_display()} Ref: {self.reference}",
                recorded_by=self.recorded_by
            )


class CashReconciliation(models.Model):
    """
    Physical cash count reconciliation against system Cash in Hand.
    Flags any cash surplus or deficit.
    """
    STATUS_BALANCED = 'balanced'
    STATUS_SURPLUS = 'surplus'
    STATUS_SHORTAGE = 'shortage'

    STATUS_CHOICES = [
        (STATUS_BALANCED, 'Exact Balance'),
        (STATUS_SURPLUS, 'Cash Surplus (Physical > System)'),
        (STATUS_SHORTAGE, 'Cash Shortage (Physical < System)'),
    ]

    reconciliation_date = models.DateField(default=timezone.now)
    system_cash = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Expected cash in hand calculated by the system."
    )
    actual_cash = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Physical cash counted."
    )
    variance = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Variance = Physical Cash - System Cash. Positive is surplus, negative is shortage."
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    # Denomination breakdown (KES notes & coins)
    notes_1000 = models.PositiveIntegerField(default=0, help_text="Number of KES 1,000 notes")
    notes_500 = models.PositiveIntegerField(default=0, help_text="Number of KES 500 notes")
    notes_200 = models.PositiveIntegerField(default=0, help_text="Number of KES 200 notes")
    notes_100 = models.PositiveIntegerField(default=0, help_text="Number of KES 100 notes")
    notes_50 = models.PositiveIntegerField(default=0, help_text="Number of KES 50 notes")
    coins_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text="Total value of coins")

    notes = models.TextField(blank=True, help_text="Explanations, reasons for variance, or remarks.")
    reconciled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reconciliation_date', '-created_at']
        verbose_name = 'Cash Reconciliation'
        verbose_name_plural = 'Cash Reconciliations'

    def __str__(self):
        return f"Cash Recon {self.reconciliation_date} — Variance: KES {self.variance:,.2f} ({self.get_status_display()})"


class BankReconciliation(models.Model):
    """
    Bank statement reconciliation against system Bank ledger balance.
    Flags any unreconciled variance.
    """
    STATUS_RECONCILED = 'reconciled'
    STATUS_UNRECONCILED = 'unreconciled'

    STATUS_CHOICES = [
        (STATUS_RECONCILED, 'Reconciled (Balanced)'),
        (STATUS_UNRECONCILED, 'Unreconciled Difference'),
    ]

    bank_account = models.ForeignKey('bank_accounts.BankAccount', on_delete=models.PROTECT, related_name='reconciliations')
    statement_date = models.DateField(default=timezone.now)
    statement_balance = models.DecimalField(max_digits=14, decimal_places=2, help_text="Ending balance on official bank statement.")
    ledger_balance = models.DecimalField(max_digits=14, decimal_places=2, help_text="System bank balance on statement date.")
    variance = models.DecimalField(max_digits=14, decimal_places=2, help_text="Variance = Statement Balance - System Ledger Balance.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    unreconciled_items_notes = models.TextField(blank=True, help_text="List of uncredited cheques, outstanding withdrawals, or bank charges.")
    notes = models.TextField(blank=True)
    reconciled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-statement_date', '-created_at']
        verbose_name = 'Bank Reconciliation'
        verbose_name_plural = 'Bank Reconciliations'

    def __str__(self):
        return f"{self.bank_account} Recon on {self.statement_date} — Diff: KES {self.variance:,.2f}"
