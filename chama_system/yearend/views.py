from django.views.generic import ListView, CreateView, DetailView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from decimal import Decimal, ROUND_DOWN

from accounts.mixins import TreasurerRequiredMixin
from members.models import Member
from contributions.models import Contribution
from penalties.models import Penalty
from loans.models import Loan
from utils.financials import get_available_fund_balance

from .models import YearEndWithdrawal, MemberInterestShare, YearEndMemberStatus
from .forms import YearEndWithdrawalForm


def _compute_year_end_distribution(members, financial_year=None):
    """
    Compute the year-end distribution for all active members.

    Step 1: Each member gets back their total contributions + registration fee.
    Step 2: Remaining balance = Total Income − SUM(contributions + reg fees for all members)
    Step 3: Remaining balance (profit pool) is shared PROPORTIONATELY to each member's
            contributions. Member with higher contributions gets a larger profit share.

            member_share = (member_contributions / total_contributions) × profit_pool

    Returns a dict with:
        member_breakdown: list of {member, contributions, reg_fee, principal_back, interest_share, total}
        total_contributions_back: sum of all contributions returned
        total_reg_fees_back: sum of all reg fees returned
        total_principal_back: total_contributions_back + total_reg_fees_back
        remaining_balance: profit pool to share proportionately
        total_payout: total amount to be withdrawn
        member_count: number of active members
    """
    from contributions.models import Contribution
    from penalties.models import Penalty
    from loans.models import Loan

    # --- Total income ---
    total_contributions_income = (
        Contribution.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    )
    total_reg_fees_income = (
        Member.objects.aggregate(t=Sum('registration_fee'))['t'] or Decimal('0')
    )
    total_penalties_income = (
        Penalty.objects.filter(paid=True).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    )
    # Interest collected per loan
    from django.db.models import F, ExpressionWrapper, DecimalField
    loans_qs = Loan.objects.annotate(
        interest_charged=ExpressionWrapper(
            F('total_payable') - F('loan_amount'),
            output_field=DecimalField(),
        )
    ).only('amount_paid', 'total_payable', 'loan_amount')
    interest_collected = sum(
        min(l.amount_paid, l.interest_charged) for l in loans_qs
    )
    total_income = (
        total_contributions_income
        + total_reg_fees_income
        + Decimal(str(interest_collected))
        + total_penalties_income
    )

    # --- Per-member principal back (contributions + reg fee) ---
    member_breakdown = []
    total_principal_back = Decimal('0')
    total_member_contributions = Decimal('0')  # used for proportional sharing

    for m in members:
        contrib = m.total_contributions() or Decimal('0')
        reg_fee = m.registration_fee or Decimal('0')
        principal = contrib + reg_fee
        total_principal_back += principal
        total_member_contributions += contrib
        member_breakdown.append({
            'member': m,
            'contributions': contrib,
            'reg_fee': reg_fee,
            'principal_back': principal,
        })

    # --- Remaining balance (profit pool) ---
    remaining_balance = max(total_income - total_principal_back, Decimal('0'))

    # --- Proportional profit share per member ---
    # Each member's share = (their contributions / total contributions) × profit pool
    # If no contributions at all, fall back to equal split
    for row in member_breakdown:
        if total_member_contributions > 0 and remaining_balance > 0:
            row['interest_share'] = (
                (row['contributions'] / total_member_contributions) * remaining_balance
            ).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        else:
            # Fallback: equal split if no contributions recorded
            count = len(member_breakdown)
            row['interest_share'] = (
                (remaining_balance / count).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                if count > 0 else Decimal('0')
            )
        row['total'] = row['principal_back'] + row['interest_share']

    total_interest_shared = sum(r['interest_share'] for r in member_breakdown)
    total_payout = total_principal_back + total_interest_shared

    return {
        'member_breakdown': member_breakdown,
        'total_contributions_back': total_contributions_income,
        'total_reg_fees_back': total_reg_fees_income,
        'total_principal_back': total_principal_back,
        'remaining_balance': remaining_balance,
        'total_interest_shared': total_interest_shared,
        'total_payout': total_payout,
        'member_count': len(member_breakdown),
        'total_income': total_income,
        'total_member_contributions': total_member_contributions,
    }


class YearEndListView(TreasurerRequiredMixin, ListView):
    model = YearEndWithdrawal
    template_name = 'yearend/yearend_list.html'
    context_object_name = 'withdrawals'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['available_fund_balance'] = get_available_fund_balance()
        return ctx


class YearEndDetailView(TreasurerRequiredMixin, DetailView):
    model = YearEndWithdrawal
    template_name = 'yearend/yearend_detail.html'
    context_object_name = 'withdrawal'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['interest_shares'] = (
            self.object.interest_shares.select_related('member').order_by('member__name')
        )
        ctx['member_statuses'] = (
            self.object.member_statuses.select_related('member').order_by('member__name')
        )
        return ctx


class YearEndCreateView(TreasurerRequiredMixin, CreateView):
    model = YearEndWithdrawal
    form_class = YearEndWithdrawalForm
    template_name = 'yearend/yearend_form.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        members = list(Member.objects.filter(is_active=True).order_by('name'))
        distribution = _compute_year_end_distribution(members)
        ctx.update(distribution)
        ctx['available_fund_balance'] = get_available_fund_balance()
        return ctx

    def form_valid(self, form):
        members = list(Member.objects.filter(is_active=True).order_by('name'))
        post = self.request.POST

        # --- Collect member statuses ---
        member_statuses = {}
        for m in members:
            member_statuses[m.pk] = post.get(f'status_{m.pk}', 'continuing')

        # --- Validate: exiting members must have no active/late loans ---
        exiting_with_loans = []
        for m in members:
            if member_statuses.get(m.pk) == 'exiting':
                if Loan.objects.filter(member=m, status__in=['active', 'late']).exists():
                    exiting_with_loans.append(m.name)

        if exiting_with_loans:
            names = ', '.join(exiting_with_loans)
            messages.error(
                self.request,
                f'The following members have outstanding loans and cannot exit: {names}. '
                f'Please ensure all loans are cleared before marking them as exiting.'
            )
            return self.form_invalid(form)

        # --- Compute distribution ---
        distribution = _compute_year_end_distribution(members)

        with transaction.atomic():
            withdrawal = form.save(commit=False)
            withdrawal.recorded_by = self.request.user
            # Auto-set amount_withdrawn and interest_shared from computed distribution
            withdrawal.amount_withdrawn = distribution['total_payout']
            withdrawal.interest_shared = distribution['total_interest_shared']
            withdrawal.save()

            # Save per-member interest shares (computed automatically)
            for row in distribution['member_breakdown']:
                MemberInterestShare.objects.create(
                    withdrawal=withdrawal,
                    member=row['member'],
                    amount=row['interest_share'],
                )

            # Save member statuses + update is_active for exiting members
            for m in members:
                status = member_statuses.get(m.pk, 'continuing')
                YearEndMemberStatus.objects.create(
                    withdrawal=withdrawal, member=m, status=status
                )
                if status == 'exiting':
                    Member.objects.filter(pk=m.pk).update(is_active=False)

        messages.success(
            self.request,
            f'Year-end withdrawal for {withdrawal.financial_year} recorded. '
            f'Total payout: KES {withdrawal.amount_withdrawn:,.2f}'
        )
        return super(CreateView, self).form_valid(form)

    def get_success_url(self):
        return reverse_lazy('yearend:detail', kwargs={'pk': self.object.pk})
