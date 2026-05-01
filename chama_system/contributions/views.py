from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.views import View
from django.urls import reverse_lazy
from django.db.models import Q
from .models import Contribution
from .forms import ContributionForm
from members.models import Member
from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin, MemberAccessMixin, AdminPasswordDeleteMixin
from utils.exports import export_csv, export_pdf
from datetime import date
from django.utils import timezone


class ContributionListView(MemberAccessMixin, ListView):
    model = Contribution
    template_name = 'contributions/contribution_list.html'
    context_object_name = 'contributions'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('member')
        q = self.request.GET.get('q', '').strip()
        month = self.request.GET.get('month', '').strip()
        year = self.request.GET.get('year', '').strip()
        if q:
            qs = qs.filter(member__name__icontains=q)
        if month:
            qs = qs.filter(month=month)
        if year:
            qs = qs.filter(year=year)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_month'] = self.request.GET.get('month', '')
        ctx['selected_year'] = self.request.GET.get('year', '')
        ctx['months'] = [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)]
        ctx['years'] = range(today.year - 3, today.year + 1)
        return ctx


class ContributionCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = Contribution
    form_class = ContributionForm
    template_name = 'contributions/contribution_form.html'
    success_url = reverse_lazy('contributions:add')
    success_message = "Contribution recorded. Add another below."


class ContributionUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Contribution
    form_class = ContributionForm
    template_name = 'contributions/contribution_form.html'
    success_url = reverse_lazy('contributions:list')
    success_message = "Contribution updated."


class ContributionDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = Contribution
    template_name = 'contributions/contribution_confirm_delete.html'
    success_url = reverse_lazy('contributions:list')


class ContributionDefaultersView(MemberAccessMixin, TemplateView):
    template_name = 'contributions/defaulters.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        month = int(self.request.GET.get('month', today.month))
        year = int(self.request.GET.get('year', today.year))

        paid_ids = Contribution.objects.filter(
            month=month, year=year
        ).values_list('member_id', flat=True)

        defaulters = Member.objects.exclude(id__in=paid_ids)
        ctx['defaulters'] = defaulters
        ctx['month'] = month
        ctx['year'] = year
        ctx['month_name'] = date(year, month, 1).strftime('%B')
        ctx['months'] = [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)]
        ctx['years'] = range(today.year - 2, today.year + 1)
        return ctx


class DefaultersExportView(MemberAccessMixin, View):
    """Export defaulters list as PDF."""
    def get(self, request):
        today = timezone.localdate()
        month = int(request.GET.get('month', today.month))
        year = int(request.GET.get('year', today.year))
        month_name = date(year, month, 1).strftime('%B')

        paid_ids = Contribution.objects.filter(
            month=month, year=year
        ).values_list('member_id', flat=True)

        defaulters = Member.objects.exclude(id__in=paid_ids).order_by('name')

        fields = [
            (lambda obj: obj.name, 'Member Name'),
            (lambda obj: obj.phone or '—', 'Phone'),
            (lambda obj: str(obj.date_joined), 'Date Joined'),
        ]

        title = f'Contribution Defaulters — {month_name} {year}'
        return export_pdf(defaulters, 'defaulters', title, fields)


class ContributionExportView(MemberAccessMixin, View):
    """Export contributions as CSV or PDF."""
    def get(self, request):
        format_type = request.GET.get('format', 'csv')
        qs = Contribution.objects.select_related('member').all()
        
        # Apply same filters as list view
        q = request.GET.get('q', '').strip()
        month = request.GET.get('month', '').strip()
        year = request.GET.get('year', '').strip()
        if q:
            qs = qs.filter(member__name__icontains=q)
        if month:
            qs = qs.filter(month=month)
        if year:
            qs = qs.filter(year=year)
        
        fields = [
            ('member.name', 'Member'),
            (lambda obj: obj.get_month_display(), 'Month'),
            ('year', 'Year'),
            ('amount', 'Amount (KES)'),
            (lambda obj: obj.get_payment_type_display(), 'Method'),
            ('mpesa_code', 'M-Pesa Code'),
            ('date', 'Date'),
        ]
        
        if format_type == 'pdf':
            return export_pdf(qs, 'contributions', 'Contributions Report', fields, orientation='landscape')
        else:
            return export_csv(qs, 'contributions', fields)
