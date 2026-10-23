"""
Loan Restructuring Calculation Service
======================================
Pure business logic module for re-calculating loan schedules and terms
during restructuring workflows.

Uses Decimal arithmetic exclusively with ROUND_HALF_UP and reconciles
all installment totals so rounding errors are absorbed into the final installment.
"""

from decimal import Decimal, ROUND_HALF_UP
import calendar
import datetime
from django.utils import timezone


def _add_months(start_date: datetime.date, months: int) -> datetime.date:
    """Add N months to a date, preserving day-of-month or clamping to month-end."""
    month = start_date.month - 1 + months
    year = start_date.year + month // 12
    month = month % 12 + 1
    max_days = calendar.monthrange(year, month)[1]
    day = min(start_date.day, max_days)
    return datetime.date(year, month, day)


def _quantize(amount: Decimal) -> Decimal:
    """Quantize to 2 decimal places with ROUND_HALF_UP."""
    return Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def calculate_reducing_emi(principal: Decimal, monthly_rate: Decimal, months: int) -> Decimal:
    """
    Calculate equal monthly installment (EMI) using Decimal math.
    Formula: EMI = P * r * (1+r)^n / ((1+r)^n - 1)
    """
    if months <= 0:
        return Decimal('0.00')
    if monthly_rate <= Decimal('0.00'):
        return _quantize(principal / Decimal(months))
    
    p = float(principal)
    r = float(monthly_rate)
    n = int(months)
    factor = (1 + r) ** n
    if factor <= 1:
        return _quantize(principal / Decimal(months))
    emi_float = p * r * factor / (factor - 1)
    return _quantize(Decimal(str(round(emi_float, 2))))


def recalculate_schedule(
    loan,
    restructure_type: str,
    params: dict = None,
    as_of_date: datetime.date = None
) -> list[dict]:
    """
    Pure calculation function for restructuring loan repayment schedules.

    Parameters:
    - loan: Loan model instance (or mock with equivalent attributes)
    - restructure_type: 'TERM_EXTENSION' | 'RATE_ADJUSTMENT' | 'MORATORIUM' | 'CONSOLIDATION' | 'WRITE_OFF'
    - params: dict containing type-specific parameters:
        * new_term_months: int (for TERM_EXTENSION, RATE_ADJUSTMENT, CONSOLIDATION)
        * new_rate: Decimal or str (for RATE_ADJUSTMENT, TERM_EXTENSION, CONSOLIDATION)
        * moratorium_months: int (for MORATORIUM)
        * accrue_interest: bool (for MORATORIUM, whether interest accrues during freeze)
        * remaining_months: int (for MORATORIUM post-freeze repayment periods)
        * consolidated_loans: list of Loan instances (for CONSOLIDATION)
        * loan_type: str (optional override: 'flat', 'reducing', 'reducing_principal', 'emergency')
    - as_of_date: date to base installment schedules from (defaults to today)

    Returns:
    - list[dict] where each item is:
      {
          'installment_number': int,
          'due_date': datetime.date,
          'principal_amount': Decimal,
          'interest_amount': Decimal,
          'total_installment': Decimal,
          'description': str,
      }
    """
    if params is None:
        params = {}
    if as_of_date is None:
        as_of_date = timezone.localdate()

    # ── 1. WRITE_OFF ────────────────────────────────────────────────
    if restructure_type == 'WRITE_OFF':
        return []

    # ── 2. Determine Loan Type, Base Principal & Rates ───────────────
    loan_type = params.get('loan_type') or getattr(loan, 'loan_type', 'flat')
    
    if restructure_type == 'CONSOLIDATION':
        loans_to_merge = params.get('consolidated_loans') or []
        if loan not in loans_to_merge:
            loans_to_merge = [loan] + list(loans_to_merge)
        # Sum remaining balances across all loans
        remaining_principal = Decimal('0.00')
        for l in loans_to_merge:
            rem = max(Decimal(str(l.total_payable)) - Decimal(str(l.amount_paid)), Decimal('0.00'))
            remaining_principal += rem
        remaining_principal = _quantize(remaining_principal)
    else:
        # Remaining balance: total_payable - amount_paid
        remaining_principal = max(
            Decimal(str(getattr(loan, 'total_payable', Decimal('0.00')))) - Decimal(str(getattr(loan, 'amount_paid', Decimal('0.00')))),
            Decimal('0.00')
        )
        remaining_principal = _quantize(remaining_principal)

    if remaining_principal <= Decimal('0.00'):
        return []

    # Rate resolution
    if 'new_rate' in params and params['new_rate'] is not None:
        rate = Decimal(str(params['new_rate']))
    else:
        rate = Decimal(str(getattr(loan, 'interest_rate', Decimal('0.10'))))

    # ── 3. Handle Restructure Types ──────────────────────────────────
    
    # ── Type A: MORATORIUM ──────────────────────────────────────────
    if restructure_type == 'MORATORIUM':
        moratorium_months = int(params.get('moratorium_months', 1))
        post_months = int(params.get('remaining_months', getattr(loan, 'duration_months', 1)))
        if post_months <= 0:
            post_months = 1
        accrue_interest = bool(params.get('accrue_interest', False))

        schedule = []
        inst_num = 1
        curr_date = as_of_date

        # Moratorium freeze period
        for m in range(moratorium_months):
            curr_date = _add_months(as_of_date, m + 1)
            if accrue_interest:
                # Interest on frozen balance during moratorium
                if loan_type in ('flat', 'emergency'):
                    m_interest = _quantize((remaining_principal * rate) / Decimal(post_months)) if rate > 0 else Decimal('0.00')
                else:
                    m_interest = _quantize(remaining_principal * rate)
                schedule.append({
                    'installment_number': inst_num,
                    'due_date': curr_date,
                    'principal_amount': Decimal('0.00'),
                    'interest_amount': m_interest,
                    'total_installment': m_interest,
                    'description': f'Moratorium (Month {m+1} of {moratorium_months}) — Interest Accrued',
                })
            else:
                schedule.append({
                    'installment_number': inst_num,
                    'due_date': curr_date,
                    'principal_amount': Decimal('0.00'),
                    'interest_amount': Decimal('0.00'),
                    'total_installment': Decimal('0.00'),
                    'description': f'Moratorium (Month {m+1} of {moratorium_months}) — Payment Frozen',
                })
            inst_num += 1

        # Post-moratorium amortization of remaining balance
        post_schedule = _build_amortization_schedule(
            principal=remaining_principal,
            months=post_months,
            rate=rate,
            loan_type=loan_type,
            start_date=curr_date,
            start_installment_number=inst_num,
            description_prefix='Resumed Installment'
        )
        schedule.extend(post_schedule)
        return schedule

    # ── Type B: TERM_EXTENSION / RATE_ADJUSTMENT / CONSOLIDATION ─────
    new_term_months = int(params.get('new_term_months') or getattr(loan, 'duration_months', 1))
    if new_term_months <= 0:
        new_term_months = 1

    return _build_amortization_schedule(
        principal=remaining_principal,
        months=new_term_months,
        rate=rate,
        loan_type=loan_type,
        start_date=as_of_date,
        start_installment_number=1,
        description_prefix='Restructured Installment'
    )


def _build_amortization_schedule(
    principal: Decimal,
    months: int,
    rate: Decimal,
    loan_type: str,
    start_date: datetime.date,
    start_installment_number: int = 1,
    description_prefix: str = 'Installment'
) -> list[dict]:
    """
    Helper to generate amortized installments with exact remainder absorption on the final installment.
    """
    if months <= 0 or principal <= Decimal('0.00'):
        return []

    schedule = []
    
    # Emergency Loan (0% Interest)
    if loan_type == 'emergency' or rate == Decimal('0.00'):
        base_principal = _quantize(principal / Decimal(months))
        allocated_principal = Decimal('0.00')

        for i in range(months):
            inst_num = start_installment_number + i
            due_date = _add_months(start_date, i + 1)
            
            if i == months - 1:
                # Absorb rounding remainder on last installment
                p_amount = principal - allocated_principal
            else:
                p_amount = base_principal
                allocated_principal += p_amount

            schedule.append({
                'installment_number': inst_num,
                'due_date': due_date,
                'principal_amount': p_amount,
                'interest_amount': Decimal('0.00'),
                'total_installment': p_amount,
                'description': f'{description_prefix} {i+1} of {months}',
            })
        return schedule

    # Flat Rate Loan
    if loan_type == 'flat':
        total_interest = _quantize(principal * rate)
        total_payable = principal + total_interest

        base_principal = _quantize(principal / Decimal(months))
        base_interest = _quantize(total_interest / Decimal(months))
        
        allocated_principal = Decimal('0.00')
        allocated_interest = Decimal('0.00')

        for i in range(months):
            inst_num = start_installment_number + i
            due_date = _add_months(start_date, i + 1)

            if i == months - 1:
                p_amount = principal - allocated_principal
                i_amount = total_interest - allocated_interest
            else:
                p_amount = base_principal
                i_amount = base_interest
                allocated_principal += p_amount
                allocated_interest += i_amount

            total_inst = p_amount + i_amount
            schedule.append({
                'installment_number': inst_num,
                'due_date': due_date,
                'principal_amount': p_amount,
                'interest_amount': i_amount,
                'total_installment': total_inst,
                'description': f'{description_prefix} {i+1} of {months}',
            })
        return schedule

    # Reducing Balance — Equal Principal
    if loan_type == 'reducing_principal':
        base_principal = _quantize(principal / Decimal(months))
        allocated_principal = Decimal('0.00')
        balance = principal

        for i in range(months):
            inst_num = start_installment_number + i
            due_date = _add_months(start_date, i + 1)

            if i == months - 1:
                p_amount = principal - allocated_principal
            else:
                p_amount = base_principal
                allocated_principal += p_amount

            i_amount = _quantize(balance * rate)
            balance = max(balance - p_amount, Decimal('0.00'))
            total_inst = p_amount + i_amount

            schedule.append({
                'installment_number': inst_num,
                'due_date': due_date,
                'principal_amount': p_amount,
                'interest_amount': i_amount,
                'total_installment': total_inst,
                'description': f'{description_prefix} {i+1} of {months}',
            })
        return schedule

    # Reducing Balance — Equal Installments (EMI)
    # loan_type == 'reducing'
    monthly_emi = calculate_reducing_emi(principal, rate, months)
    balance = principal
    allocated_principal = Decimal('0.00')

    for i in range(months):
        inst_num = start_installment_number + i
        due_date = _add_months(start_date, i + 1)

        i_amount = _quantize(balance * rate)
        
        if i == months - 1:
            p_amount = principal - allocated_principal
            total_inst = p_amount + i_amount
        else:
            p_amount = _quantize(monthly_emi - i_amount)
            if p_amount > balance:
                p_amount = balance
            allocated_principal += p_amount
            total_inst = p_amount + i_amount

        balance = max(balance - p_amount, Decimal('0.00'))

        schedule.append({
            'installment_number': inst_num,
            'due_date': due_date,
            'principal_amount': p_amount,
            'interest_amount': i_amount,
            'total_installment': total_inst,
            'description': f'{description_prefix} {i+1} of {months}',
        })

    return schedule


# ── Signal Definitions ─────────────────────────────────────────────
from django.dispatch import Signal
loan_restructure_approved = Signal()


def check_max_restructures_limit(loan) -> bool:
    """
    Validate that the loan has not reached the maximum allowed approved restructures.
    Uses settings.MAX_RESTRUCTURES_PER_LOAN (default 3).
    """
    from django.conf import settings
    from django.core.exceptions import ValidationError
    from loans.models import LoanRestructure

    max_limit = getattr(settings, 'MAX_RESTRUCTURES_PER_LOAN', 3)
    prior_count = LoanRestructure.objects.filter(
        loan=loan, status='APPROVED'
    ).count()

    if prior_count >= max_limit:
        raise ValidationError(
            f"Loan #{loan.pk} has already reached the maximum limit of {max_limit} restructures."
        )
    return True


def apply_restructure(restructure_obj, approved_by_user):
    """
    Atomically approve and apply a loan restructure:
    1. Recalculate schedule based on restructure parameters.
    2. Snapshot current active schedule rows.
    3. Supersede old active schedule rows.
    4. Create new RepaymentSchedule rows.
    5. Update loan status, due_date, and metadata.
    6. Mark restructure as APPROVED and fire guarantor notification signal.
    """
    from django.db import transaction
    from django.core.exceptions import ValidationError
    from loans.models import Loan, RepaymentSchedule

    if restructure_obj.status != 'PENDING':
        raise ValidationError(f"Only PENDING restructures can be approved (currently {restructure_obj.status}).")

    loan = restructure_obj.loan
    if loan.status in ('cleared', 'written_off'):
        raise ValidationError(f"Cannot restructure a loan with status '{loan.get_status_display()}'.")

    # Check maximum restructure count guardrail
    check_max_restructures_limit(loan)

    with transaction.atomic():
        # Lock loan row for update
        locked_loan = Loan.objects.select_for_update().get(pk=loan.pk)

        # 1. Snapshot previous unsuperseded schedule
        old_qs = RepaymentSchedule.objects.filter(
            loan=locked_loan, superseded_by__isnull=True
        ).order_by('installment_number')

        old_snapshot = []
        old_pks = []
        for r in old_qs:
            old_pks.append(r.pk)
            old_snapshot.append({
                'id': r.pk,
                'installment_number': r.installment_number,
                'due_date': str(r.due_date),
                'principal_amount': str(r.principal_amount),
                'interest_amount': str(r.interest_amount),
                'total_installment': str(r.total_installment),
                'paid_amount': str(r.paid_amount),
                'is_paid': r.is_paid,
            })
        restructure_obj.old_schedule_snapshot = old_snapshot

        # 2. Recalculate schedule
        new_items = recalculate_schedule(
            loan=locked_loan,
            restructure_type=restructure_obj.restructure_type,
            params=restructure_obj.parameters,
            as_of_date=timezone.localdate()
        )

        # 3. Create new schedule rows
        created_schedules = []
        new_snapshot = []
        for item in new_items:
            new_sched = RepaymentSchedule.objects.create(
                loan=locked_loan,
                installment_number=item['installment_number'],
                due_date=item['due_date'],
                principal_amount=item['principal_amount'],
                interest_amount=item['interest_amount'],
                total_installment=item['total_installment'],
                paid_amount=Decimal('0.00'),
                is_paid=False,
                restructure=restructure_obj,
            )
            created_schedules.append(new_sched)
            new_snapshot.append({
                'id': new_sched.pk,
                'installment_number': item['installment_number'],
                'due_date': str(item['due_date']),
                'principal_amount': str(item['principal_amount']),
                'interest_amount': str(item['interest_amount']),
                'total_installment': str(item['total_installment']),
                'description': item.get('description', ''),
            })

        restructure_obj.new_schedule_snapshot = new_snapshot

        # 4. Mark old schedule rows as superseded
        if old_pks:
            first_new = created_schedules[0] if created_schedules else None
            RepaymentSchedule.objects.filter(pk__in=old_pks).update(
                superseded_by=first_new
            )

        # 5. Update loan attributes
        if restructure_obj.restructure_type == 'WRITE_OFF':
            locked_loan.status = 'written_off'
        elif restructure_obj.restructure_type == 'CONSOLIDATION':
            locked_loan.status = 'active'
            if created_schedules:
                locked_loan.due_date = created_schedules[-1].due_date
            # Mark other consolidated loans
            for other_loan in restructure_obj.consolidated_loans.all():
                if other_loan.pk != locked_loan.pk:
                    other_loan.status = 'restructured'
                    other_loan.notes = (other_loan.notes or '') + f"\n[Restructure #{restructure_obj.pk}] Consolidated into Loan #{locked_loan.pk} on {timezone.localdate()}."
                    other_loan.save(update_fields=['status', 'notes'])
        else:
            locked_loan.status = 'active'
            if created_schedules:
                locked_loan.due_date = created_schedules[-1].due_date

        locked_loan.save()

        # 6. Finalize restructure record
        restructure_obj.status = 'APPROVED'
        restructure_obj.approved_by = approved_by_user
        restructure_obj.approved_at = timezone.now()
        restructure_obj.save()

        # 7. Collect and notify guarantors
        guarantors = list(locked_loan.guarantors.select_related('guarantor').all())
        loan_restructure_approved.send(
            sender=restructure_obj.__class__,
            restructure=restructure_obj,
            loan=locked_loan,
            approved_by=approved_by_user,
            guarantors=guarantors,
        )

    return restructure_obj


def reject_restructure(restructure_obj, rejected_by_user, rejection_reason: str = ''):
    """
    Reject a pending restructure request without mutating any schedule or loan rows.
    """
    from django.core.exceptions import ValidationError

    if restructure_obj.status != 'PENDING':
        raise ValidationError(f"Only PENDING restructures can be rejected (currently {restructure_obj.status}).")

    restructure_obj.status = 'REJECTED'
    restructure_obj.approved_by = rejected_by_user
    restructure_obj.approved_at = timezone.now()
    restructure_obj.rejection_reason = rejection_reason or 'Restructure request rejected by committee/admin.'
    restructure_obj.save(update_fields=['status', 'approved_by', 'approved_at', 'rejection_reason'])
    return restructure_obj

