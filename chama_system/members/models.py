from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.utils import timezone
from decimal import Decimal


class RegistrationFeeRate(models.Model):
    """
    Configurable registration fee rate for all members.
    All members pay the same amount when they join.
    """
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Fixed registration fee amount for all members.',
    )
    effective_date = models.DateField(
        help_text='Date from which this rate is effective.',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-effective_date']
        verbose_name_plural = 'Registration Fee Rates'

    def __str__(self):
        return f"KES {self.amount} from {self.effective_date}"

    @classmethod
    def current_rate(cls):
        """Return the rate in effect today, or None if none configured."""
        today = timezone.localdate()
        return cls.objects.filter(effective_date__lte=today).first()


class RegistrationFeePayment(models.Model):
    """
    Tracks individual registration fee payments for each member.
    Records when and how much was paid.
    """
    member = models.ForeignKey(
        'Member',
        on_delete=models.CASCADE,
        related_name='fee_payments',
    )
    
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Amount paid for registration fee.',
    )
    
    payment_date = models.DateField(
        default=timezone.localdate,
        help_text='Date when the registration fee was paid.',
    )
    
    payment_method = models.CharField(
        max_length=20,
        choices=[
            ('cash', 'Cash'),
            ('mpesa', 'M-Pesa'),
            ('bank_transfer', 'Bank Transfer'),
            ('cheque', 'Cheque'),
        ],
        default='cash',
    )
    
    receipt_number = models.CharField(
        max_length=100, blank=True,
        help_text='Receipt or reference number for payment.',
    )
    
    notes = models.TextField(blank=True)
    
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='fee_payments_recorded',
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-payment_date']
        verbose_name_plural = 'Registration Fee Payments'
        indexes = [
            models.Index(fields=['member', '-payment_date']),
        ]
    
    def __str__(self):
        try:
            name = self.member.name
        except Exception:
            name = f"Member #{self.member_id}"
        return f"{name} - KES {self.amount:,.2f} ({self.payment_date})"


class Member(models.Model):
    # ── Core fields ───────────────────────────────────────────────
    name             = models.CharField(max_length=200)
    phone            = models.CharField(max_length=20, unique=True)
    registration_fee_paid = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Registration fee amount paid by this member when they joined.',
    )
    date_joined = models.DateField(default=timezone.localdate)
    is_active   = models.BooleanField(default=True)

    # ── Photo & ID document ───────────────────────────────────────
    photo = models.ImageField(
        upload_to='members/photos/',
        blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])],
        help_text='Passport-style photo (JPG/PNG, max 5 MB).',
    )
    id_document = models.FileField(
        upload_to='members/id_docs/',
        blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
        help_text='National ID, passport scan, or any official ID document (PDF/JPG/PNG).',
    )

    # ── Next of kin / beneficiary ─────────────────────────────────
    next_of_kin_name         = models.CharField(max_length=200, blank=True)
    next_of_kin_phone        = models.CharField(max_length=20, blank=True)
    next_of_kin_relationship = models.CharField(
        max_length=100, blank=True,
        help_text='e.g. Spouse, Parent, Sibling, Child',
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def total_contributions(self):
        return self.contribution_set.aggregate(
            total=models.Sum('amount')
        )['total'] or 0

    def total_welfare(self):
        return self.welfare_contributions.aggregate(
            total=models.Sum('amount')
        )['total'] or 0

    def total_loans(self):
        return self.loan_set.aggregate(
            total=models.Sum('loan_amount')
        )['total'] or 0

    def total_loan_balance(self):
        from django.db.models import Sum, F, ExpressionWrapper, DecimalField
        result = self.loan_set.exclude(status='cleared').aggregate(
            balance=Sum(
                ExpressionWrapper(
                    F('total_payable') - F('amount_paid'),
                    output_field=DecimalField()
                )
            )
        )['balance']
        return max(result or Decimal('0'), Decimal('0'))

    def total_penalties_unpaid(self):
        return self.penalties.filter(paid=False).aggregate(
            t=models.Sum('amount')
        )['t'] or Decimal('0.00')


class MemberExit(models.Model):
    """
    Records a member's voluntary exit from the chama.

    net_payout = contributions_returned + reg_fee_returned
               + profit_share_paid
               - outstanding_loans_deducted
               - outstanding_penalties_deducted
    """
    member = models.OneToOneField(
        Member,
        on_delete=models.PROTECT,
        related_name='exit_record',
    )
    exit_date = models.DateField()

    # Amounts owed to the member
    contributions_returned = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Total contributions paid in by the member.',
    )
    reg_fee_returned = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Registration fee returned to the member.',
    )
    profit_share_paid = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Pro-rated profit share allocated to the member.',
    )

    # Amounts deducted from the member
    outstanding_loans_deducted = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Outstanding loan balance deducted from payout.',
    )
    outstanding_penalties_deducted = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Unpaid penalty amounts deducted from payout.',
    )

    # Net amount actually paid out
    net_payout = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
    )

    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='member_exits_recorded',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-exit_date']

    def __str__(self):
        return f"{self.member.name} exited on {self.exit_date} — KES {self.net_payout:,.2f}"


from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver([post_save, post_delete], sender=RegistrationFeePayment)
def update_member_registration_fee_paid(sender, instance, **kwargs):
    if instance.member_id:
        total = RegistrationFeePayment.objects.filter(member_id=instance.member_id).aggregate(t=models.Sum('amount'))['t'] or Decimal('0.00')
        Member.objects.filter(pk=instance.member_id).update(registration_fee_paid=total)
