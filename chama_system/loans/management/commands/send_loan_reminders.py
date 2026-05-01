from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from loans.models import Loan


class Command(BaseCommand):
    help = (
        'Print a reminder list of loans due within the next 7 days '
        'and loans that are already late. '
        'Extend this command to send SMS/email when a gateway is configured.'
    )

    def handle(self, *args, **kwargs):
        today = timezone.localdate()
        upcoming_cutoff = today + timedelta(days=7)

        # Loans due within the next 7 days (still active)
        upcoming = Loan.objects.filter(
            status='active',
            due_date__gte=today,
            due_date__lte=upcoming_cutoff,
        ).select_related('member').order_by('due_date')

        # Already late loans
        late = Loan.objects.filter(
            status='late',
        ).select_related('member').order_by('due_date')

        self.stdout.write(self.style.WARNING(
            f'\\n=== Loans Due in the Next 7 Days ({upcoming.count()}) ==='
        ))
        for loan in upcoming:
            days_left = (loan.due_date - today).days
            self.stdout.write(
                f'  #{loan.pk} {loan.member.name} | '
                f'Balance: KES {loan.balance:,.2f} | '
                f'Due: {loan.due_date} ({days_left} day(s) left)'
            )

        self.stdout.write(self.style.ERROR(
            f'\\n=== Late Loans ({late.count()}) ==='
        ))
        for loan in late:
            overdue_days = (today - loan.due_date).days if loan.due_date else '?'
            self.stdout.write(
                f'  #{loan.pk} {loan.member.name} | '
                f'Balance: KES {loan.balance:,.2f} | '
                f'Due: {loan.due_date} ({overdue_days} days overdue) | '
                f'Penalties applied: {loan.late_penalty_months} month(s)'
            )

        self.stdout.write(self.style.SUCCESS(
            f'\\nDone. {upcoming.count()} upcoming, {late.count()} late.'
        ))