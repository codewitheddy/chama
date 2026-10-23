import calendar
from datetime import date

from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal

from loans.models import Loan


class Command(BaseCommand):
    help = (
        'Mark overdue active loans as Late and apply monthly late penalties.\n'
        '\n'
        'Flat-rate loans: penalty = original_principal x rate (fixed each month).\n'
        'Reducing-balance loans: penalty = outstanding_balance x rate (dynamic,\n'
        '  mirrors the original EMI logic — same rate on whatever is still owed).'
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

            if months_to_apply <= 0:
                continue

            if loan.loan_type in ('flat', 'emergency'):
                # ── Flat loans: fixed penalty per month ───────────────────
                # original_principal × rate, charged regardless of payments.
                _, base_total, _ = loan._compute_interest()
                new_acc = (
                    loan.late_penalty_per_month * overdue_months
                ).quantize(Decimal('0.01'))
                new_total = (
                    base_total + new_acc
                ).quantize(Decimal('0.01'))

            else:
                # ── Reducing-balance loans: penalty on outstanding balance ─
                # Apply each missing month one at a time so each month's penalty
                # is computed on the balance AFTER the previous month's penalty
                # was added (compound — same as how EMI interest accrues).
                loan.refresh_from_db()
                rate = (
                    Decimal(str(loan.interest_rate))
                    if loan.interest_rate is not None
                    else Decimal('0.10')
                )
                running_total = loan.total_payable
                running_acc = loan.accumulated_penalties or Decimal('0.00')
                for _ in range(months_to_apply):
                    outstanding = max(running_total - loan.amount_paid, Decimal('0.00'))
                    monthly_penalty = (outstanding * rate).quantize(Decimal('0.01'))
                    running_acc = (running_acc + monthly_penalty).quantize(Decimal('0.01'))
                    running_total = (running_total + monthly_penalty).quantize(Decimal('0.01'))
                new_acc = running_acc
                new_total = running_total

            Loan.objects.filter(pk=loan.pk).update(
                late_penalty_months=overdue_months,
                accumulated_penalties=new_acc,
                total_payable=new_total,
                status='late',
            )
            penalties_applied += months_to_apply
            self.stdout.write(
                f'  Loan #{loan.pk} ({loan.get_loan_type_display()}) — '
                f'{months_to_apply} penalty month(s) applied. '
                f'New total: KES {new_total:,.2f}'
            )

        self.stdout.write(self.style.SUCCESS(
            f'{penalties_applied} penalty month(s) applied across {late_loans.count()} late loan(s).'
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
