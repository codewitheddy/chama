from django.apps import AppConfig


class BackupConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'backup'
    verbose_name = 'Backup & Restore'

    def ready(self):
        try:
            from .scheduler import start_scheduler
            start_scheduler()
        except Exception:
            pass
