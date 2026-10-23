from django.apps import AppConfig
from django.db.models.signals import post_migrate


def auto_upgrade_welfare_bank_on_migrate(sender, **kwargs):
    try:
        from utils.reconciler import reconcile_bank_accounts
        reconcile_bank_accounts()
    except Exception:
        pass


class BankAccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'bank_accounts'
    verbose_name = 'Bank Accounts'

    def ready(self):
        post_migrate.connect(auto_upgrade_welfare_bank_on_migrate, sender=self)
