from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from audit.models import AuditLog
from .models import Investment, InvestmentValuation, InvestmentReturn, InvestmentWithdrawal


@receiver(post_save, sender=Investment)
def log_investment_save(sender, instance, created, **kwargs):
    """Log investment creation and updates."""
    if created:
        AuditLog.objects.create(
            user=instance.recorded_by,
            action='create',
            app_label='investments',
            model_name='investment',
            object_id=instance.pk,
            object_repr=str(instance),
            changes={'initial_amount': str(instance.initial_amount)},
        )


@receiver(post_delete, sender=Investment)
def log_investment_delete(sender, instance, **kwargs):
    """Log investment deletion."""
    AuditLog.objects.create(
        user=None,
        action='delete',
        app_label='investments',
        model_name='investment',
        object_id=instance.pk,
        object_repr=str(instance),
    )


@receiver(post_save, sender=InvestmentValuation)
def log_valuation_save(sender, instance, created, **kwargs):
    """Log valuation creation."""
    if created:
        AuditLog.objects.create(
            user=instance.valuation_by,
            action='create',
            app_label='investments',
            model_name='investmentvaluation',
            object_id=instance.pk,
            object_repr=str(instance),
            changes={'current_value': str(instance.current_value)},
        )


@receiver(post_save, sender=InvestmentReturn)
def log_return_save(sender, instance, created, **kwargs):
    """Log return creation."""
    if created:
        AuditLog.objects.create(
            user=instance.recorded_by,
            action='create',
            app_label='investments',
            model_name='investmentreturn',
            object_id=instance.pk,
            object_repr=str(instance),
            changes={'amount': str(instance.amount)},
        )


@receiver(post_save, sender=InvestmentWithdrawal)
def log_withdrawal_save(sender, instance, created, **kwargs):
    """Log withdrawal creation."""
    if created:
        AuditLog.objects.create(
            user=instance.recorded_by,
            action='create',
            app_label='investments',
            model_name='investmentwithdrawal',
            object_id=instance.pk,
            object_repr=str(instance),
            changes={'amount_received': str(instance.amount_received)},
        )
