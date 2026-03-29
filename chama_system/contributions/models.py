from django.db import models
from members.models import Member


MONTH_CHOICES = [
    (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
    (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
    (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
]


class Contribution(models.Model):
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    month = models.IntegerField(choices=MONTH_CHOICES)
    year = models.IntegerField(default=2024)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.member.name} - {self.get_month_display()} {self.year}"
