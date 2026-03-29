from django.db import models
from django.utils import timezone


class Member(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, unique=True)
    registration_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    date_joined = models.DateField(default=timezone.localdate)

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
        return sum(l.balance for l in self.loan_set.all())
