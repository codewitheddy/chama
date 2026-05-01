from django.db import models
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.conf import settings
from decimal import Decimal
from members.models import Member

# Read from settings so it can be changed without touching code.
INTEREST_RATE = Decimal(str(getattr(settings, 'LOAN_INTEREST_RATE', 0.10)))


class Loan(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('cleared', 'Cleared'),
        ('late', 'Late'),
    ]

    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    loan_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    duration_months = models.PositiveIntegerField(default=1)
    interest_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        editable=False,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    total_payable = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        editable=False,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    date_taken = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    rollover_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    # Late-penalty tracking
    late_penalty_per_month = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        editable=False,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Fixed monthly penalty amount (10% of original principal).",
    )
    late_penalty_months = models.PositiveIntegerField(
        default=0,
        editable=False,
        help_text="Number of overdue months for which the penalty has been applied.",
    )

    class Meta:
        ordering = ['-date_taken']

    def save(self, *args, **kwargs):
        principal = Decimal(str(self.loan_amount))
        self.interest_amount = (principal * INTEREST_RATE).quantize(Decimal('0.01'))

        # Set the fixed monthly penalty (10% of principal) once at creation.
        if not self.pk:
            self.late_penalty_per_month = self.interest_amount
            self.late_penalty_months = 0

        # total_payable = principal + interest + accumulated late penalties
        accumulated_penalties = self.late_penalty_per_month * self.late_penalty_months
        self.total_payable = (principal + self.interest_amount + accumulated_penalties).quantize(Decimal('0.01'))

        if self.date_taken and not self.due_date:
            import calendar
            from django.utils import timezone as tz
            month = self.date_taken.month - 1 + self.duration_months
            year = self.date_taken.year + month // 12
            month = month % 12 + 1
            day = min(self.date_taken.day, calendar.monthrange(year, month)[1])
            self.due_date = tz.localdate().replace(year=year, month=month, day=day)

        # Determine status — cleared takes priority, then late, then active
        from django.utils import timezone as tz
        today = tz.localdate()
        if self.amount_paid >= self.total_payable:
            self.status = 'cleared'
        elif self.due_date and today > self.due_date:
            self.status = 'late'
        elif self.status == 'cleared':
            self.status = 'active'
        elif self.status not in ('late', 'active'):
            self.status = 'active'

        super().save(*args, **kwargs)

    def apply_late_penalty(self):
        """
        Add one month's penalty to this loan.
        Called by the mark_late_loans management command once per overdue month.
        Uses update() to avoid triggering the full save() recalculation loop.
        """
        new_months = self.late_penalty_months + 1
        new_total = (
            self.loan_amount
            + self.interest_amount
            + self.late_penalty_per_month * new_months
        ).quantize(Decimal('0.01'))
        Loan.objects.filter(pk=self.pk).update(
            late_penalty_months=new_months,
            total_payable=new_total,
            status='late',
        )
        self.refresh_from_db()

    def do_rollover(self, duration_months=None):
        """
        Roll over the loan:
        - The outstanding balance becomes the new principal
        - A fresh 10% interest is charged on that balance
        - due_date is extended by duration_months (defaults to original duration)
        - A LoanRollover record is created for audit trail
        """
        import calendar
        from django.db import transaction
        from django.utils import timezone as tz

        outstanding = self.balance
        new_interest = (outstanding * INTEREST_RATE).quantize(Decimal('0.01'))
        new_total = outstanding + new_interest

        months = duration_months or self.duration_months
        base = tz.localdate()
        month = base.month - 1 + months
        year = base.year + month // 12
        month = month % 12 + 1
        day = min(base.day, calendar.monthrange(year, month)[1])
        new_due = base.replace(year=year, month=month, day=day)

        with transaction.atomic():
            LoanRollover.objects.create(
                loan=self,
                balance_before=outstanding,
                new_interest=new_interest,
                new_total=new_total,
                rolled_on=tz.localdate(),
            )
            Loan.objects.filter(pk=self.pk).update(
                loan_amount=outstanding,
                interest_amount=new_interest,
                total_payable=new_total,
                amount_paid=Decimal('0.00'),
                due_date=new_due,
                status='active',
                rollover_count=self.rollover_count + 1,
            )
        self.refresh_from_db()

    @property
    def balance(self):
        return max(self.total_payable - self.amount_paid, Decimal('0'))

    @property
    def repayment_percent(self):
        if self.total_payable == 0:
            return 0
        return min(int((self.amount_paid / self.total_payable) * 100), 100)

    @property
    def total_guaranteed(self):
        from django.db.models import Sum
        return self.guarantors.aggregate(t=Sum('amount_guaranteed'))['t'] or Decimal('0.00')

    @property
    def guarantee_coverage_percent(self):
        if self.loan_amount == 0:
            return 0
        return min(int((self.total_guaranteed / self.loan_amount) * 100), 100)

    @staticmethod
    def has_active_loan(member):
        return Loan.objects.filter(member=member, status__in=['active', 'late']).exists()

    def __str__(self):
        return f"#{self.pk} {self.member.name} — KES {self.loan_amount}"


class LoanRollover(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='rollovers')
    balance_before = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    new_interest = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    new_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    rolled_on = models.DateField()

    class Meta:
        ordering = ['rolled_on']

    def __str__(self):
        return f"Rollover #{self.pk} for Loan #{self.loan_id} on {self.rolled_on}"


class LoanGuarantor(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='guarantors')
    guarantor = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='guarantees'
    )
    amount_guaranteed = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('loan', 'guarantor')

    def __str__(self):
        return f"{self.guarantor.name} guarantees KES {self.amount_guaranteed} for Loan #{self.loan.pk}"


class Collateral(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='collaterals')
    description = models.CharField(max_length=255)
    estimated_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    document = models.FileField(
        upload_to='collateral_docs/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.description} (KES {self.estimated_value}) — Loan #{self.loan.pk}"
