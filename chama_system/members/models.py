from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal


class Member(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, unique=True)
    registration_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    date_joined = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def total_contributions(self):
        return self.contribution_set.aggregate(
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
