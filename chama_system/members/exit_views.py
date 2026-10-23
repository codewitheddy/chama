"""
Member exit views.

Two-step flow:
  1. GET  /members/<pk>/exit/preview/  — show exit summary and any blocking issues
  2. POST /members/<pk>/exit/confirm/  — record the exit (only allowed if member owes nothing)

A member CANNOT exit if they have:
  - Any active or late loans
  - Any unpaid penalties

Both must be fully cleared before the exit button is enabled.
"""
from decimal import Decimal, ROUND_DOWN

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from accounts.mixins import TreasurerRequiredMixin
from .models import Member, MemberExit


# ── Helper ────────────────────────────────────────────────────────────────────

def _compute_exit_summary(member):
    """
    Compute the full exit picture for a member.

    Registration fee is NON-REFUNDABLE — it is NOT included in the payout.

    Returns a dict:
        contributions       – total contributions paid in (refunded)
        reg_fee             – registration fee (NON-refundable, shown for info only)
        profit_share        – pro-rated profit share
        gross_payout        – contributions + profit_share (NO reg fee)
        net_payout          – same as gross (member must clear debts first)

        active_loans        – QS of active/late loans (blocker)
        unpaid_penalties    – QS of unpaid penalties (blocker)
        loan_balance        – total outstanding loan amount
        penalty_balance     – total unpaid penalty amount
        is_blocked          – True if member owes ANYTHING
        blockers            – list of blocking reason strings
    """
    from django.db.models import Sum
    from contributions.models import Contribution
    from penalties.models import Penalty
    from loans.models import Loan
    from yearend.views import _compute_year_end_distribution

    # ── What they contributed ─────────────────────────────────────
    contributions = (
        Contribution.objects.filter(member=member).aggregate(t=Sum('amount'))['t']
        or Decimal('0')
    )
    reg_fee = member.registration_fee_paid or Decimal('0')

    # ── Pro-rated profit share ────────────────────────────────────
    try:
        from django.db.models import Sum, F, ExpressionWrapper, DecimalField
        from contributions.models import Contribution as _C
        from loans.models import Loan as _L
        from penalties.models import Penalty as _P

        # Total income — reg fees excluded (separate fund)
        total_contrib_income = _C.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        total_pen_income     = _P.objects.filter(paid=True).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        loans_qs = _L.objects.annotate(
            interest_charged=ExpressionWrapper(F('total_payable') - F('loan_amount'), output_field=DecimalField())
        ).only('amount_paid', 'total_payable', 'loan_amount')
        interest_collected = sum(min(l.amount_paid, l.interest_charged) for l in loans_qs)
        total_income = total_contrib_income + Decimal(str(interest_collected)) + total_pen_income

        my_contrib = Decimal(str(contributions))
        total_all_contrib = _C.objects.filter(member__is_active=True).aggregate(t=Sum('amount'))['t'] or Decimal('0')

        # Principal back = contributions only; reg fees excluded from year-end
        profit_pool = max(total_income - total_all_contrib, Decimal('0'))

        profit_share = (
            (my_contrib / total_all_contrib * profit_pool).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            if total_all_contrib > 0 and profit_pool > 0 else Decimal('0')
        )
    except Exception:
        profit_share = Decimal('0')

    if hasattr(profit_share, 'quantize'):
        profit_share = profit_share.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
    else:
        profit_share = Decimal(str(profit_share)).quantize(Decimal('0.01'))

    gross_payout = contributions + profit_share  # reg_fee is NON-REFUNDABLE

    # ── What they owe ─────────────────────────────────────────────
    active_loans = Loan.objects.filter(member=member, status__in=['active', 'late'])
    loan_balance = member.total_loan_balance()

    unpaid_penalties = Penalty.objects.filter(member=member, paid=False)
    penalty_balance = (
        unpaid_penalties.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    )

    # ── Build blockers list ───────────────────────────────────────
    blockers = []
    if active_loans.exists():
        count = active_loans.count()
        blockers.append(
            f'{count} outstanding loan{"s" if count > 1 else ""} '
            f'totalling KES {loan_balance:,.2f} must be fully repaid.'
        )
    if unpaid_penalties.exists():
        count = unpaid_penalties.count()
        blockers.append(
            f'{count} unpaid penalt{"ies" if count > 1 else "y"} '
            f'totalling KES {penalty_balance:,.2f} must be settled.'
        )

    is_blocked = bool(blockers)

    return {
        'contributions':    contributions,
        'reg_fee':          reg_fee,
        'profit_share':     profit_share,
        'gross_payout':     gross_payout,
        'net_payout':       gross_payout,   # no deductions — member cleared before exit
        'active_loans':     active_loans,
        'unpaid_penalties': unpaid_penalties,
        'loan_balance':     loan_balance,
        'penalty_balance':  penalty_balance,
        'is_blocked':       is_blocked,
        'blockers':         blockers,
    }


# ── Views ─────────────────────────────────────────────────────────────────────

class MemberExitPreviewView(TreasurerRequiredMixin, View):
    """
    Step 1 – show the exit summary.
    If the member still owes anything, the confirm button is hidden and
    the blocking issues are listed clearly.
    """
    template_name = 'members/member_exit_preview.html'

    def get(self, request, pk):
        member = get_object_or_404(Member, pk=pk)

        if hasattr(member, 'exit_record'):
            messages.info(request, f'{member.name} has already exited.')
            return redirect('members:exit_detail', pk=pk)

        if not member.is_active:
            messages.warning(request, f'{member.name} is already inactive.')
            return redirect('members:detail', pk=pk)

        summary = _compute_exit_summary(member)
        return render(request, self.template_name, {'member': member, **summary})


class MemberExitConfirmView(TreasurerRequiredMixin, View):
    """
    Step 2 – record the exit.
    Hard-blocks if the member has ANY outstanding loans or unpaid penalties.
    No override / force option — debts must be cleared first.
    """
    template_name = 'members/member_exit_preview.html'

    def post(self, request, pk):
        member = get_object_or_404(Member, pk=pk)

        if hasattr(member, 'exit_record'):
            messages.info(request, f'{member.name} has already exited.')
            return redirect('members:exit_detail', pk=pk)

        if not member.is_active:
            messages.warning(request, f'{member.name} is already inactive.')
            return redirect('members:detail', pk=pk)

        summary = _compute_exit_summary(member)

        # ── Hard block — do not proceed if anything is owed ──────
        if summary['is_blocked']:
            for reason in summary['blockers']:
                messages.error(request, reason)
            return render(request, self.template_name, {'member': member, **summary})

        notes     = request.POST.get('notes', '').strip()
        exit_date = request.POST.get('exit_date', '').strip() or str(timezone.localdate())

        with transaction.atomic():
            MemberExit.objects.create(
                member=member,
                exit_date=exit_date,
                contributions_returned=summary['contributions'],
                reg_fee_returned=Decimal('0.00'),      # non-refundable
                profit_share_paid=summary['profit_share'],
                outstanding_loans_deducted=Decimal('0.00'),
                outstanding_penalties_deducted=Decimal('0.00'),
                net_payout=summary['net_payout'],
                notes=notes,
                recorded_by=request.user,
            )
            Member.objects.filter(pk=member.pk).update(is_active=False)

        messages.success(
            request,
            f'{member.name} has been exited successfully. '
            f'Net payout: KES {summary["net_payout"]:,.2f}.'
        )
        return redirect('members:exit_detail', pk=pk)


class MemberExitDetailView(TreasurerRequiredMixin, View):
    """Show the recorded exit receipt for a member."""
    template_name = 'members/member_exit_detail.html'

    def get(self, request, pk):
        member = get_object_or_404(Member, pk=pk)
        exit_record = get_object_or_404(MemberExit, member=member)
        return render(request, self.template_name, {
            'member': member,
            'exit_record': exit_record,
        })


class MemberExitListView(TreasurerRequiredMixin, View):
    """List all member exits."""
    template_name = 'members/member_exit_list.html'

    def get(self, request):
        exits = MemberExit.objects.select_related('member', 'recorded_by').order_by('-exit_date')
        return render(request, self.template_name, {'exits': exits})
