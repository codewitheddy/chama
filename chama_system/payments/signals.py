from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from .models import Payment


def update_loan_amount_paid(loan_id):
    """
    Recalculate amount_paid and status for a loan from its payment records.
    Uses select_for_update() inside a transaction to prevent race conditions
    when two payments are recorded simultaneously.

    If the loan was funded from a bank account, also updates the bank balance
    snapshot to reflect repayments:
        bank_balance = pre_disbursement_balance - loan_amount + total_repaid
    """
    from django.db.models import Sum
    from decimal import Decimal
    from django.utils import timezone
    from loans.models import Loan

    if not loan_id:
        return

    with transaction.atomic():
        # Lock the loan row to prevent concurrent updates
        try:
            loan = Loan.objects.select_for_update().get(pk=loan_id)
        except Loan.DoesNotExist:
            return
        if loan.last_rollover_date:
            total = loan.payment_set.filter(date__gte=loan.last_rollover_date).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        else:
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

        # ── Bank balance update for bank-funded loans ──────────────────
        if loan.fund_source == 'bank_account' and loan.fund_source_bank:
            _update_bank_balance_for_loan(loan, total)


def _update_bank_balance_for_loan(loan, total_repaid):
    """
    Keep the bank balance in sync with repayments on a bank-funded loan.

    Strategy:
      1. Find the disbursement snapshot (the BankBalance row created when
         the loan was issued, identified by notes containing 'Loan #<id>').
      2. Get the balance that existed just BEFORE that disbursement snapshot
         — that is the true pre-disbursement balance.
      3. Compute:
             correct_balance = pre_disbursement_balance - loan_amount + total_repaid
      4. Upsert a dedicated repayment-tracking snapshot so the bank's
         current_balance always reflects the real position.
    """
    from decimal import Decimal
    from django.utils import timezone
    from bank_accounts.models import BankAccount, BankBalance

    bank_account = loan.fund_source_bank
    # Find the disbursement snapshot for this specific loan
    disburse_snapshot = (
        BankBalance.objects
        .filter(
            account=bank_account,
            notes__contains=f'Loan #{loan.pk}',
            transaction_type=BankBalance.TYPE_DEDUCTION
        )
        .order_by('recorded_on', 'created_at')
        .first()
    )

    if disburse_snapshot is None:
        # Fallback: check any note starting with Loan #<id>
        disburse_snapshot = (
            BankBalance.objects
            .filter(account=bank_account, notes__startswith=f'Loan #{loan.pk}')
            .order_by('recorded_on', 'created_at')
            .first()
        )

    if disburse_snapshot is None:
        # Disbursement snapshot missing (e.g. pre-fix legacy loan) — skip
        return

    # Get the snapshot that was current just before the disbursement.
    # BankBalance is ordered -recorded_on, -created_at so "just before"
    # means recorded_on < disburse date OR same date but created earlier.
    pre_disburse_snapshot = (
        BankBalance.objects
        .filter(account=bank_account)
        .exclude(pk=disburse_snapshot.pk)
        .filter(
            # created strictly before the disbursement snapshot
            created_at__lt=disburse_snapshot.created_at
        )
        .order_by('-recorded_on', '-created_at')
        .first()
    )

    pre_disburse_balance = (
        pre_disburse_snapshot.balance
        if pre_disburse_snapshot
        else Decimal('0.00')
    )

    # correct running balance after partial/full repayment
    correct_balance = pre_disburse_balance - loan.loan_amount + total_repaid

    # Clamp to zero just in case of rounding
    correct_balance = max(correct_balance, Decimal('0.00'))

    repayment_note_marker = f'Loan #{loan.pk} repayment'

    # Find an existing repayment-tracking snapshot to update (upsert pattern)
    existing = (
        BankBalance.objects
        .filter(account=bank_account, notes__startswith=repayment_note_marker)
        .order_by('created_at')
        .first()
    )

    today = timezone.localdate()
    note = (
        f'Loan #{loan.pk} repayment tracking — '
        f'principal KES {loan.loan_amount:,.2f}, '
        f'repaid KES {total_repaid:,.2f} of KES {loan.total_payable:,.2f}.'
    )

    if existing:
        if total_repaid == Decimal('0.00'):
            existing.delete()
        else:
            existing.balance     = correct_balance
            existing.recorded_on = today
            existing.notes       = note
            existing.save(update_fields=['balance', 'recorded_on', 'notes'])
    else:
        if total_repaid > Decimal('0.00'):
            BankBalance.objects.create(
                account=bank_account,
                balance=correct_balance,
                topup_amount=total_repaid,
                transaction_type=BankBalance.TYPE_TOPUP,
                recorded_on=today,
                notes=note,
            )


@receiver(post_save, sender=Payment)
def on_payment_save(sender, instance, created, **kwargs):
    if created:
        update_loan_amount_paid(instance.loan_id)


@receiver(post_delete, sender=Payment)
def on_payment_delete(sender, instance, **kwargs):
    update_loan_amount_paid(instance.loan_id)
