from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.http import HttpResponse
from django.db.models import Sum
import csv
from members.models import Member
from contributions.models import Contribution
from loans.models import Loan
from payments.models import Payment


class IncomeReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/income_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_reg_fees'] = Member.objects.aggregate(t=Sum('registration_fee'))['t'] or 0
        ctx['total_contributions'] = Contribution.objects.aggregate(t=Sum('amount'))['t'] or 0
        ctx['total_loans_given'] = Loan.objects.aggregate(t=Sum('loan_amount'))['t'] or 0
        ctx['total_interest'] = Loan.objects.aggregate(t=Sum('interest_amount'))['t'] or 0
        ctx['total_income'] = ctx['total_reg_fees'] + ctx['total_contributions'] + ctx['total_interest']
        return ctx


class ContributionReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/contribution_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['members'] = Member.objects.all()
        ctx['contributions'] = Contribution.objects.select_related('member').all()
        return ctx


class LoanReportView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/loan_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['loans'] = Loan.objects.select_related('member').all()
        ctx['total_issued'] = Loan.objects.aggregate(t=Sum('loan_amount'))['t'] or 0
        ctx['total_paid'] = Loan.objects.aggregate(t=Sum('amount_paid'))['t'] or 0
        ctx['total_balance'] = sum(l.balance for l in Loan.objects.all())
        return ctx


class MemberStatementView(LoginRequiredMixin, TemplateView):
    template_name = 'reports/member_statement.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        member_id = self.request.GET.get('member')
        ctx['members'] = Member.objects.all()
        if member_id:
            try:
                from loans.models import LoanGuarantor
                member = Member.objects.get(pk=member_id)
                ctx['selected_member'] = member
                ctx['contributions'] = member.contribution_set.all()
                ctx['loans'] = member.loan_set.all()
                ctx['payments'] = member.payment_set.all()
                ctx['guarantees'] = LoanGuarantor.objects.filter(
                    guarantor=member
                ).select_related('loan__member')
            except Member.DoesNotExist:
                pass
        return ctx


class ExportContributionsCSV(LoginRequiredMixin, TemplateView):
    def get(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="contributions.csv"'
        w = csv.writer(response)
        w.writerow(['Member', 'Amount', 'Month', 'Year', 'Date'])
        for c in Contribution.objects.select_related('member').all():
            w.writerow([c.member.name, c.amount, c.get_month_display(), c.year, c.date])
        return response


class ExportLoansCSV(LoginRequiredMixin, TemplateView):
    def get(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="loans.csv"'
        w = csv.writer(response)
        w.writerow(['Member', 'Loan Amount', 'Duration', 'Interest', 'Total Payable', 'Amount Paid', 'Balance', 'Status', 'Date Taken', 'Due Date'])
        for l in Loan.objects.select_related('member').all():
            w.writerow([l.member.name, l.loan_amount, l.duration_months, l.interest_amount,
                        l.total_payable, l.amount_paid, l.balance, l.get_status_display(),
                        l.date_taken, l.due_date])
        return response


class ExportPaymentsCSV(LoginRequiredMixin, TemplateView):
    def get(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="payments.csv"'
        w = csv.writer(response)
        w.writerow(['Member', 'Loan Amount', 'Payment Amount', 'Date', 'Notes'])
        for p in Payment.objects.select_related('member', 'loan').all():
            w.writerow([p.member.name, p.loan.loan_amount, p.amount, p.date, p.notes])
        return response


class ExportMembersCSV(LoginRequiredMixin, TemplateView):
    def get(self, request):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="members.csv"'
        w = csv.writer(response)
        w.writerow(['Name', 'Phone', 'Registration Fee', 'Date Joined', 'Total Contributions', 'Total Loans', 'Loan Balance'])
        for m in Member.objects.all():
            w.writerow([m.name, m.phone, m.registration_fee, m.date_joined,
                        m.total_contributions(), m.total_loans(), m.total_loan_balance()])
        return response
