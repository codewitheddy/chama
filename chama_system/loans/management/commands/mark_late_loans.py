from django.core.management.base import BaseCommand
from django.utils import timezone
from loans.models import Loan


class Command(BaseCommand):
    help = 'Mark overdue active loans as Late'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        updated = Loan.objects.filter(
            status='active',
            due_date__lt=today
        ).update(status='late')
        self.stdout.write(self.style.SUCCESS(f'{updated} loan(s) marked as Late.'))
