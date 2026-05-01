"""
Management command: purge_recycle_bin

Permanently deletes all DeletedRecord entries that have exceeded the
retention period (default 30 days).

Usage:
    python manage.py purge_recycle_bin
    python manage.py purge_recycle_bin --dry-run

Schedule with cron or a task scheduler to run daily, e.g.:
    0 2 * * * /path/to/venv/bin/python /path/to/manage.py purge_recycle_bin
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from recycle_bin.models import DeletedRecord


class Command(BaseCommand):
    help = 'Permanently purge recycle bin records older than the retention period.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting.',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=DeletedRecord.RETENTION_DAYS,
            help=f'Retention period in days (default: {DeletedRecord.RETENTION_DAYS}).',
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        cutoff = timezone.now() - timedelta(days=days)

        expired = DeletedRecord.objects.filter(deleted_at__lte=cutoff)
        count = expired.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('No expired records to purge.'))
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[DRY RUN] Would permanently delete {count} record(s) '
                    f'older than {days} days.'
                )
            )
            for r in expired:
                self.stdout.write(f'  - {r.model_name} #{r.object_id}: {r.object_repr} '
                                  f'(deleted {r.deleted_at.strftime("%Y-%m-%d")})')
        else:
            expired.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f'Purged {count} expired record(s) from the recycle bin.'
                )
            )
