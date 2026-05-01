from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from decimal import Decimal


class YearEndWithdrawal(models.Model):
    """Records the group's annual savings distribution event."""
    financial_year = models.PositiveIntegerField(unique=True)
    amount_withdrawn = models.DecimalField(
        max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    interest_shared = models.DecimalField(
        max_digits=14, decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    date = models.DateField()
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        editable=False,
        related_name='year_end_withdrawals',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-financial_year']

    def __str__(self):
        return f"Year-End {self.financial_year} — KES {self.amount_withdrawn:,.2f}"


class MemberInterestShare(models.Model):
    """Per-member interest share for a year-end withdrawal event."""
    withdrawal = models.ForeignKey(
        YearEndWithdrawal, on_delete=models.CASCADE,
        related_name='interest_shares',
    )
    member = models.ForeignKey(
        'members.Member', on_delete=models.PROTECT,
        related_name='interest_shares',
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )

    class Meta:
        unique_together = ('withdrawal', 'member')
        ordering = ['member__name']

    def __str__(self):
        return f"{self.member.name} — KES {self.amount:,.2f} ({self.withdrawal.financial_year})"


class YearEndMemberStatus(models.Model):
    """Records whether each member is continuing or exiting at year-end."""
    STATUS_CHOICES = [('continuing', 'Continuing'), ('exiting', 'Exiting')]

    withdrawal = models.ForeignKey(
        YearEndWithdrawal, on_delete=models.CASCADE,
        related_name='member_statuses',
    )
    member = models.ForeignKey(
        'members.Member', on_delete=models.PROTECT,
        related_name='year_end_statuses',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='continuing')

    class Meta:
        unique_together = ('withdrawal', 'member')
        ordering = ['member__name']

    def __str__(self):
        return f"{self.member.name} — {self.get_status_display()} ({self.withdrawal.financial_year})"
