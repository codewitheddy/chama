from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from members.models import Member
from contributions.models import Contribution
from loans.models import Loan
from payments.models import Payment
from penalties.models import Penalty
from django.utils import timezone
import json


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        total_members = Member.objects.count()
        total_contributions = Contribution.objects.aggregate(t=Sum('amount'))['t'] or 0
        total_reg_fees = Member.objects.aggregate(t=Sum('registration_fee'))['t'] or 0
        total_loans_given = Loan.objects.aggregate(t=Sum('loan_amount'))['t'] or 0
        # Projected = interest charged on ALL loans (including penalties already applied)
        projected_qs = Loan.objects.aggregate(
            t=Sum(
                ExpressionWrapper(
                    F('total_payable') - F('loan_amount'),
                    output_field=DecimalField()
                )
            )
        )
        total_interest_projected = projected_qs['t'] or 0

        # Interest actually collected using interest-first payment allocation.
        # min(amount_paid, total_payable - loan_amount) per loan — done in DB.
        # We use a single query with annotation instead of a Python loop.
        from django.db.models import Min as _Min
        loans_qs = Loan.objects.annotate(
            interest_charged=ExpressionWrapper(
                F('total_payable') - F('loan_amount'),
                output_field=DecimalField()
            )
        )
        # Python loop is unavoidable for min() per-row, but we fetch only 3 fields
        interest_collected_total = sum(
            min(l.amount_paid, l.interest_charged)
            for l in loans_qs.only('amount_paid', 'total_payable', 'loan_amount')
        )
        total_interest_collected = interest_collected_total

        # Total loan balance (active+late) — single DB query
        balance_qs = Loan.objects.filter(status__in=['active', 'late']).aggregate(
            bal=Sum(
                ExpressionWrapper(
                    F('total_payable') - F('amount_paid'),
                    output_field=DecimalField()
                )
            )
        )
        total_loan_balance = max(balance_qs['bal'] or 0, 0)

        total_loan_paid = Loan.objects.aggregate(t=Sum('amount_paid'))['t'] or 0
        total_penalties = Penalty.objects.filter(paid=True).aggregate(t=Sum('amount'))['t'] or 0
        total_income = total_contributions + total_reg_fees + total_interest_collected + total_penalties

        # Principal outstanding — single DB query
        # Only actual cash lent out (loan_amount) minus repayments — NOT interest
        active_loans_list = list(Loan.objects.filter(
            status__in=['active', 'late']
        ).only('loan_amount', 'amount_paid', 'interest_amount', 'total_payable'))
        principal_outstanding = sum(
            max(l.loan_amount - l.amount_paid, 0) for l in active_loans_list
        )
        # Outstanding interest = interest not yet collected on active/late loans
        outstanding_interest = sum(
            max(min(l.interest_amount, l.total_payable - l.amount_paid), 0)
            for l in active_loans_list
        )
        from utils.financials import get_available_fund_balance
        treasurer_balance = get_available_fund_balance()
        available_fund_balance = treasurer_balance

        # Chart data — contributions per month (current year)
        today_year = timezone.localdate().year
        contrib_by_month = (
            Contribution.objects.filter(year=today_year)
            .values('month').annotate(total=Sum('amount')).order_by('month')
        )
        contrib_chart = [0] * 12
        for row in contrib_by_month:
            contrib_chart[row['month'] - 1] = float(row['total'])

        from django.db.models.functions import ExtractMonth as _ExtractMonth
        loan_by_month = (
            Loan.objects.filter(date_taken__year=today_year)
            .annotate(month=_ExtractMonth('date_taken'))
            .values('month').annotate(total=Sum('loan_amount')).order_by('month')
        )
        loan_chart = [0] * 12
        for row in loan_by_month:
            if row['month']:
                loan_chart[row['month'] - 1] = float(row['total'])

        ctx.update({
            'total_members': total_members,
            'total_contributions': total_contributions,
            'total_reg_fees': total_reg_fees,
            'total_loans_given': total_loans_given,
            'total_interest_projected': total_interest_projected,
            'total_interest_collected': total_interest_collected,
            'total_loan_balance': total_loan_balance,
            'total_loan_paid': total_loan_paid,
            'total_income': total_income,
            'total_penalties': total_penalties,
            'treasurer_balance': treasurer_balance,
            'available_fund_balance': available_fund_balance,
            'principal_outstanding': principal_outstanding,
            'outstanding_interest': outstanding_interest,
            'recent_contributions': Contribution.objects.select_related('member').order_by('-date')[:5],
            'recent_loans': Loan.objects.select_related('member').order_by('-date_taken')[:5],
            'recent_payments': Payment.objects.select_related('member').order_by('-date')[:5],
            'contrib_chart_data': json.dumps(contrib_chart),
            'loan_chart_data': json.dumps(loan_chart),
            'chart_year': today_year,
        })
        return ctx