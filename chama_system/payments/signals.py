from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Payment


def update_loan_amount_paid(loan):
    from django.db.models import Sum
    from decimal import Decimal
    total = loan.payment_set.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    loan.amount_paid = total
    # recalculate status without triggering full save logic
    if total >= loan.total_payable:
        loan.status = 'cleared'
    elif loan.status == 'cleared':
        loan.status = 'active'
    # use update_fields to avoid re-triggering the full save() chain
    type(loan).objects.filter(pk=loan.pk).update(
        amount_paid=loan.amount_paid,
        status=loan.status,
    )


@receiver(post_save, sender=Payment)
def on_payment_save(sender, instance, created, **kwargs):
    if created:
        update_loan_amount_paid(instance.loan)


@receiver(post_delete, sender=Payment)
def on_payment_delete(sender, instance, **kwargs):
    update_loan_amount_paid(instance.loan)
