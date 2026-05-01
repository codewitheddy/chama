import calendar
from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal

from loans.models import Loan


class Command(BaseCommand):
    help = (
        'Mark overdue active loans as Late, and apply a monthly penalty '
        '(10% of original principal) for each overdue month not yet charged.'
    )

    def handle(self, *args, **kwargs):
        today = timezone.now().date()

        # 1. Promote active loans that have passed their due date to 'late'.
        newly_late = Loan.objects.filter(
            status='active',
            due_date__lt=today,
        ).update(status='late')
        self.stdout.write(self.style.SUCCESS(
            f'{newly_late} loan(s) newly marked as Late.'
        ))

        # 2. For every late loan, work out how many full overdue months have
        #    elapsed since the due date and apply any penalties not yet charged.
        late_loans = Loan.objects.filter(status='late')
        penalties_applied = 0

        for loan in late_loans:
            if not loan.due_date:
                continue

            overdue_months = self._months_overdue(loan.due_date, today)
            months_to_apply = overdue_months - loan.late_penalty_months

            if months_to_apply > 0:
                new_months = overdue_months
                new_total = (
                    loan.loan_amount
                    + loan.interest_amount
                    + loan.late_penalty_per_month * new_months
                ).quantize(Decimal('0.01'))
                Loan.objects.filter(pk=loan.pk).update(
                    late_penalty_months=new_months,
                    total_payable=new_total,
                    status='late',
                )
                penalties_applied += months_to_apply

        self.stdout.write(self.style.SUCCESS(
            f'{penalties_applied} monthly penalty/penalties applied across late loans.'
        ))

    @staticmethod
    def _months_overdue(due_date: date, today: date) -> int:
        """Return the number of full calendar months between due_date and today."""
        if today <= due_date:
            return 0
        months = (today.year - due_date.year) * 12 + (today.month - due_date.month)
        # If we haven't yet reached the same day-of-month, the current month is not complete.
        if today.day < due_date.day:
            months -= 1
        return max(months, 0)