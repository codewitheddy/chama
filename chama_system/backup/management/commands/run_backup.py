"""
Management command to run manual, automatic, or scheduled backup.
Usage:
    python manage.py run_backup
    python manage.py run_backup --trigger=scheduled
    python manage.py run_backup --dir="D:/Backups/Chama"
"""

from pathlib import Path
from django.core.management.base import BaseCommand
from backup.services import create_backup_file, validate_backup_directory


class Command(BaseCommand):
    help = 'Executes a database and media backup.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--trigger',
            type=str,
            default='manual',
            choices=['manual', 'automatic', 'scheduled'],
            help='Backup trigger type.'
        )
        parser.add_argument(
            '--dir',
            type=str,
            default='',
            help='Optional custom destination directory.'
        )
        parser.add_argument(
            '--no-media',
            action='store_true',
            help='Exclude media files from the backup.'
        )

    def handle(self, *args, **options):
        trigger = options['trigger']
        custom_dir_str = options['dir']
        include_media = not options['no_media']

        target_dir = None
        if custom_dir_str.strip():
            valid, msg, norm_path = validate_backup_directory(custom_dir_str)
            if not valid:
                self.stderr.write(self.style.ERROR(f"Invalid directory: {msg}"))
                return
            target_dir = Path(norm_path)

        self.stdout.write(f"Starting {trigger} backup...")
        success, message, dest_path = create_backup_file(
            trigger=trigger,
            custom_dir=target_dir,
            include_media=include_media
        )

        if success:
            self.stdout.write(self.style.SUCCESS(message))
        else:
            self.stderr.write(self.style.ERROR(message))
