from django.db import models
from django.utils import timezone


class BackupSetting(models.Model):
    MODE_CHOICES = [
        ('manual', 'Manual (Admin backups manually)'),
        ('automatic', 'Automatic (System decides schedule & location)'),
        ('scheduled', 'Scheduled (Admin decides schedule & location)'),
    ]

    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default='manual')
    custom_location = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='Custom directory path where backups will be saved in Scheduled mode.'
    )
    schedule_interval_hours = models.PositiveIntegerField(
        default=24,
        help_text='Interval in hours between backups in Scheduled mode (e.g., 6, 12, 24, 72, 168).'
    )
    retention_count = models.PositiveIntegerField(
        default=15,
        help_text='Maximum number of backups to keep before pruning oldest (0 for unlimited).'
    )
    include_media = models.BooleanField(
        default=True,
        help_text='Include uploaded member documents and photos in backup archive.'
    )
    last_backup_at = models.DateTimeField(null=True, blank=True)
    last_backup_status = models.CharField(max_length=50, default='none')
    last_backup_file = models.CharField(max_length=255, blank=True, default='')
    last_backup_trigger = models.CharField(max_length=20, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Backup Setting'
        verbose_name_plural = 'Backup Settings'

    def __str__(self):
        return f"Backup Configuration (Mode: {self.get_mode_display()})"

    @classmethod
    def get_settings(cls):
        setting, _ = cls.objects.get_or_create(id=1)
        return setting


class BackupLog(models.Model):
    TRIGGER_CHOICES = [
        ('manual', 'Manual'),
        ('automatic', 'Automatic'),
        ('scheduled', 'Scheduled'),
        ('pre_restore', 'Pre-Restore Safety'),
    ]
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    timestamp = models.DateTimeField(default=timezone.now)
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default='manual')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success')
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size_bytes = models.BigIntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    duration_seconds = models.FloatField(default=0.0)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Backup Log'
        verbose_name_plural = 'Backup Logs'

    def __str__(self):
        return f"{self.trigger_type.capitalize()} backup on {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {self.status}"

    @property
    def file_size_mb(self):
        return round(self.file_size_bytes / (1024 * 1024), 2)
