from django.apps import AppConfig


class UpdaterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "updater"
    verbose_name = "Auto-Update System"

    def ready(self):
        # Optional startup hooks if needed
        pass
