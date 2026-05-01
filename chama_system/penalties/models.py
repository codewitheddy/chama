from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from members.models import Member


class Penalty(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='penalties')
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    date = models.DateField()
    reason = models.CharField(max_length=255)
    paid = models.BooleanField(default=False)
    paid_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-date']
        verbose_name_plural = 'Penalties'

    def __str__(self):
        return f"{self.member.name} - KES {self.amount} ({self.date})"
