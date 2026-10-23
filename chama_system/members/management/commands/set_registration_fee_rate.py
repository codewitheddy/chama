from django.core.management.base import BaseCommand
from django.utils import timezone
from members.models import RegistrationFeeRate
from decimal import Decimal


class Command(BaseCommand):
    help = 'Set or update the registration fee rate'

    def add_arguments(self, parser):
        parser.add_argument(
            'amount',
            type=float,
            help='Registration fee amount in KES'
        )
        parser.add_argument(
            '--date',
            type=str,
            default=None,
            help='Effective date (YYYY-MM-DD). Defaults to today.',
        )

    def handle(self, *args, **options):
        amount = Decimal(str(options['amount']))
        
        if options['date']:
            from datetime import datetime
            effective_date = datetime.strptime(options['date'], '%Y-%m-%d').date()
        else:
            effective_date = timezone.localdate()

        rate, created = RegistrationFeeRate.objects.get_or_create(
            effective_date=effective_date,
            defaults={'amount': amount}
        )

        if not created:
            rate.amount = amount
            rate.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"Registration fee rate set to KES {amount} effective {effective_date}"
            )
        )
