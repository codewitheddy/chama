from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from members.models import Member
from loans.models import Loan


class Payment(models.Model):
    PAYMENT_TYPE_CHOICES = [
        ('cash',  'Cash'),
        ('mpesa', 'M-Pesa'),
    ]

    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    date = models.DateField()
    payment_type = models.CharField(
        max_length=10,
        choices=PAYMENT_TYPE_CHOICES,
        default='cash',
    )
    mpesa_code = models.CharField(
        max_length=20,
        blank=True,
        help_text='M-Pesa confirmation code (required for M-Pesa payments).',
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']
        constraints = [
            models.UniqueConstraint(
                fields=['loan', 'amount', 'date'],
                name='unique_payment_per_loan_date_amount'
            )
        ]

    def __str__(self):
        return f"{self.member.name} - KES {self.amount} on {self.date}"
