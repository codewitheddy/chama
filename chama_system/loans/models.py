from django.db import models
from django.db.models import Sum
from decimal import Decimal
from members.models import Member

INTEREST_RATE = Decimal('0.10')  # flat 10% one-off


class Loan(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('cleared', 'Cleared'),
        ('late', 'Late'),
    ]

    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    loan_amount = models.DecimalField(max_digits=12, decimal_places=2)
    duration_months = models.PositiveIntegerField(default=1)
    interest_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    total_payable = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date_taken = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    rollover_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date_taken']

    def save(self, *args, **kwargs):
        principal = Decimal(str(self.loan_amount))
        self.interest_amount = (principal * INTEREST_RATE).quantize(Decimal('0.01'))
        self.total_payable = principal + self.interest_amount

        if self.date_taken and not self.due_date:
            import calendar
            month = self.date_taken.month - 1 + self.duration_months
            year = self.date_taken.year + month // 12
            month = month % 12 + 1
            day = min(self.date_taken.day, calendar.monthrange(year, month)[1])
            from datetime import date
            self.due_date = date(year, month, day)

        if self.amount_paid >= self.total_payable:
            self.status = 'cleared'
        else:
            from datetime import date
            if self.due_date and date.today() > self.due_date:
                self.status = 'late'
            elif self.status not in ('late',):
                self.status = 'active'

        super().save(*args, **kwargs)

    def do_rollover(self, duration_months=None):
        """
        Roll over the loan:
        - The outstanding balance becomes the new principal
        - A fresh 10% interest is charged on that balance
        - due_date is extended by duration_months (defaults to original duration)
        - A LoanRollover record is created for audit trail
        """
        import calendar
        from datetime import date

        outstanding = self.balance
        new_interest = (outstanding * INTEREST_RATE).quantize(Decimal('0.01'))
        new_total = outstanding + new_interest

        # log the rollover before mutating
        LoanRollover.objects.create(
            loan=self,
            balance_before=outstanding,
            new_interest=new_interest,
            new_total=new_total,
            rolled_on=date.today(),
        )

        months = duration_months or self.duration_months
        base = date.today()
        month = base.month - 1 + months
        year = base.year + month // 12
        month = month % 12 + 1
        day = min(base.day, calendar.monthrange(year, month)[1])
        new_due = date(year, month, day)

        # update loan in-place — bypass save() recalculation by using update()
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
        return self.guarantors.aggregate(t=models.Sum('amount_guaranteed'))['t'] or Decimal('0.00')

    @property
    def guarantee_coverage_percent(self):
        if self.loan_amount == 0:
            return 0
        return min(int((self.total_guaranteed / self.loan_amount) * 100), 100)

    def has_active_loan(member):
        return Loan.objects.filter(member=member, status__in=['active', 'late']).exists()

    def __str__(self):
        return f"#{self.pk} {self.member.name} — KES {self.loan_amount}"


class LoanRollover(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='rollovers')
    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    new_interest = models.DecimalField(max_digits=12, decimal_places=2)
    new_total = models.DecimalField(max_digits=12, decimal_places=2)
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
    amount_guaranteed = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('loan', 'guarantor')

    def __str__(self):
        return f"{self.guarantor.name} guarantees KES {self.amount_guaranteed} for Loan #{self.loan.pk}"


class Collateral(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='collaterals')
    description = models.CharField(max_length=255)
    estimated_value = models.DecimalField(max_digits=12, decimal_places=2)
    document = models.FileField(upload_to='collateral_docs/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.description} (KES {self.estimated_value}) — Loan #{self.loan.pk}"
