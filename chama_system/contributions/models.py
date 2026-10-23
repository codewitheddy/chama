from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.utils import timezone
from members.models import Member
from utils.payment_type_mixin import PaymentTypeMixin


def current_year():
    return timezone.now().year


MONTH_CHOICES = [
    (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
    (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
    (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
]


class Contribution(PaymentTypeMixin, models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    date = models.DateField()
    month = models.IntegerField(choices=MONTH_CHOICES)
    year = models.IntegerField(default=current_year)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        try:
            name = self.member.name
        except Exception:
            name = f"Member #{self.member_id}"
        return f"{name} - {self.get_month_display()} {self.year}"
