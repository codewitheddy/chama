from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from .models import Payment


def update_loan_amount_paid(loan_id):
    """
    Recalculate amount_paid and status for a loan from its payment records.
    Uses select_for_update() inside a transaction to prevent race conditions
    when two payments are recorded simultaneously.
    """
    from django.db.models import Sum
    from decimal import Decimal
    from django.utils import timezone
    from loans.models import Loan

    with transaction.atomic():
        # Lock the loan row to prevent concurrent updates
        loan = Loan.objects.select_for_update().get(pk=loan_id)
        total = loan.payment_set.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        loan.amount_paid = total

        # Recalculate status using the same rules as Loan.save()
        if total >= loan.total_payable:
            loan.status = 'cleared'
        elif loan.due_date and timezone.localdate() > loan.due_date:
            loan.status = 'late'
        elif loan.status == 'cleared':
            # Payment was removed and loan is no longer fully paid
            loan.status = 'active'
        elif loan.status not in ('late', 'active'):
            loan.status = 'active'

        # Use update() to avoid re-triggering the full save() chain
        Loan.objects.filter(pk=loan.pk).update(
            amount_paid=loan.amount_paid,
            status=loan.status,
        )


@receiver(post_save, sender=Payment)
def on_payment_save(sender, instance, created, **kwargs):
    if created:
        update_loan_amount_paid(instance.loan_id)


@receiver(post_delete, sender=Payment)
def on_payment_delete(sender, instance, **kwargs):
    update_loan_amount_paid(instance.loan_id)
