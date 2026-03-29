from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.db.models import Sum
from members.models import Member
from contributions.models import Contribution
from loans.models import Loan
from payments.models import Payment
from penalties.models import Penalty


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        # auto-mark overdue loans on every dashboard visit
        from datetime import date
        Loan.objects.filter(status='active', due_date__lt=date.today()).update(status='late')

        ctx = super().get_context_data(**kwargs)

        total_members = Member.objects.count()
        total_contributions = Contribution.objects.aggregate(t=Sum('amount'))['t'] or 0
        total_reg_fees = Member.objects.aggregate(t=Sum('registration_fee'))['t'] or 0
        total_loans_given = Loan.objects.aggregate(t=Sum('loan_amount'))['t'] or 0
        total_interest_projected = Loan.objects.aggregate(t=Sum('interest_amount'))['t'] or 0
        total_interest_collected = Loan.objects.filter(status='cleared').aggregate(t=Sum('interest_amount'))['t'] or 0
        total_loan_balance = sum(l.balance for l in Loan.objects.filter(status__in=['active', 'late']))
        total_loan_paid = Loan.objects.aggregate(t=Sum('amount_paid'))['t'] or 0
        total_penalties = Penalty.objects.filter(paid=True).aggregate(t=Sum('amount'))['t'] or 0
        total_income = total_contributions + total_reg_fees + total_interest_collected + total_penalties

        # Chart data — contributions per month (current year)
        import json
        today_year = __import__('datetime').date.today().year
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
            'recent_contributions': Contribution.objects.select_related('member').order_by('-date')[:5],
            'recent_loans': Loan.objects.select_related('member').order_by('-date_taken')[:5],
            'recent_payments': Payment.objects.select_related('member').order_by('-date')[:5],
            'contrib_chart_data': json.dumps(contrib_chart),
            'loan_chart_data': json.dumps(loan_chart),
            'chart_year': today_year,
        })
        return ctx
