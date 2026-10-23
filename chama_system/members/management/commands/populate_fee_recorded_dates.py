from django.core.management.base import BaseCommand
from django.utils import timezone
from members.models import Member


class Command(BaseCommand):
    help = 'Populate fee_recorded_date for existing members who have registration fees but no recorded date'

    def add_arguments(self, parser):
        parser.add_argument(
            '--use-today',
            action='store_true',
            help='Set all missing dates to today instead of date_joined',
        )

    def handle(self, *args, **options):
        use_today = options.get('use_today', False)

        # Find members with reg fees but no recorded date
        members = Member.objects.filter(
            registration_fee__gt=0,
            fee_recorded_date__isnull=True
        )

        count = members.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No members need updating.'))
            return

        updated = 0
        for member in members:
            # Use date_joined as the recorded date, or today if specified
            if use_today:
                member.fee_recorded_date = timezone.localdate()
            else:
                member.fee_recorded_date = member.date_joined

            member.save(update_fields=['fee_recorded_date'])
            updated += 1
            self.stdout.write(f"Updated {member.name}: {member.fee_recorded_date}")

        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully updated {updated} member(s).'))
