from django.db import models
from members.models import Member
from loans.models import Loan


class Payment(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
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
