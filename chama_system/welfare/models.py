from django.db import models
from django.core.validators import MinValueValidator
from django.db.models import Sum
from decimal import Decimal
import datetime


MONTH_CHOICES = [
    (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
    (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
    (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
]


class WelfareContributionRate(models.Model):
    """Configurable monthly welfare contribution amount for all members."""
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    effective_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_date']

    def __str__(self):
        return f"KES {self.amount} from {self.effective_date}"

    @classmethod
    def current_rate(cls):
        """Return the rate in effect today, or None if none configured."""
        from django.utils import timezone
        today = timezone.localdate()
        return cls.objects.filter(effective_date__lte=today).first()

    @classmethod
    def rate_for_period(cls, year, month):
        """Return the rate in effect for the first day of the given month/year."""
        period_start = datetime.date(year, month, 1)
        return cls.objects.filter(effective_date__lte=period_start).first()


class WelfareContribution(models.Model):
    """A periodic payment from a member into the welfare fund."""
    member = models.ForeignKey(
        'members.Member', on_delete=models.CASCADE,
        related_name='welfare_contributions',
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    date = models.DateField()
    month = models.IntegerField(choices=MONTH_CHOICES)
    year = models.IntegerField()

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.member.name} — KES {self.amount} ({self.get_month_display()} {self.year})"


class WelfareEvent(models.Model):
    """An emergency case opened for a specific beneficiary member."""
    STATUS_CHOICES = [('open', 'Open'), ('closed', 'Closed')]

    beneficiary = models.ForeignKey(
        'members.Member', on_delete=models.CASCADE,
        related_name='welfare_events',
    )
    description = models.TextField()
    date_opened = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')

    class Meta:
        ordering = ['-date_opened']

    def __str__(self):
        return f"Event #{self.pk} — {self.beneficiary.name} ({self.get_status_display()})"

    @property
    def disbursement_amount(self):
        """Amount paid from the fund for this event (0 if no disbursement recorded)."""
        try:
            return self.disbursement.amount
        except WelfareDisbursement.DoesNotExist:
            return Decimal('0')

    @property
    def support_total(self):
        """Sum of all member support contributions for this event."""
        return self.support_contributions.aggregate(t=Sum('amount'))['t'] or Decimal('0')

    @property
    def event_total(self):
        """Total support received: fund disbursement + member support contributions."""
        return self.disbursement_amount + self.support_total


class WelfareDisbursement(models.Model):
    """A payment from the welfare fund to a beneficiary. At most one per event."""
    event = models.OneToOneField(
        WelfareEvent, on_delete=models.CASCADE,
        related_name='disbursement',
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    date = models.DateField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Disbursement #{self.pk} — KES {self.amount} for Event #{self.event_id}"


class WelfareSupportContribution(models.Model):
    """A voluntary payment from one member directly to a beneficiary for a specific event."""
    event = models.ForeignKey(
        WelfareEvent, on_delete=models.CASCADE,
        related_name='support_contributions',
    )
    contributor = models.ForeignKey(
        'members.Member', on_delete=models.CASCADE,
        related_name='welfare_support_given',
    )
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    date = models.DateField()

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.contributor.name} → Event #{self.event_id}: KES {self.amount}"


def get_welfare_balance():
    """
    Compute the current welfare fund balance as a pure DB aggregate.
    Balance = total contributions - total disbursements.
    Never stored as a field — always computed on demand.
    """
    total_in = WelfareContribution.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    total_out = WelfareDisbursement.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    return total_in - total_out
