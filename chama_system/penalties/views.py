from datetime import date
from django.utils import timezone
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.views import View
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum
from .models import Penalty
from .forms import PenaltyForm
from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin, MemberAccessMixin
from utils.exports import export_csv, export_pdf


class PenaltyListView(MemberAccessMixin, ListView):
    model = Penalty
    template_name = 'penalties/penalty_list.html'
    context_object_name = 'penalties'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('member')
        q = self.request.GET.get('q', '').strip()
        month = self.request.GET.get('month', '').strip()
        year = self.request.GET.get('year', '').strip()
        paid = self.request.GET.get('paid', '').strip()
        if q:
            qs = qs.filter(member__name__icontains=q)
        if month:
            qs = qs.filter(date__month=month)
        if year:
            qs = qs.filter(date__year=year)
        if paid == '1':
            qs = qs.filter(paid=True)
        elif paid == '0':
            qs = qs.filter(paid=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_month'] = self.request.GET.get('month', '')
        ctx['selected_year'] = self.request.GET.get('year', '')
        ctx['selected_paid'] = self.request.GET.get('paid', '')
        ctx['months'] = [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)]
        ctx['years'] = range(today.year - 3, today.year + 1)
        qs = self.get_queryset()
        ctx['total_filtered'] = qs.aggregate(t=Sum('amount'))['t'] or 0
        ctx['total_paid'] = Penalty.objects.filter(paid=True).aggregate(t=Sum('amount'))['t'] or 0
        ctx['total_unpaid'] = Penalty.objects.filter(paid=False).aggregate(t=Sum('amount'))['t'] or 0
        return ctx


class PenaltyCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = Penalty
    form_class = PenaltyForm
    template_name = 'penalties/penalty_form.html'
    success_url = reverse_lazy('penalties:list')
    success_message = "Penalty recorded."


class PenaltyUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Penalty
    form_class = PenaltyForm
    template_name = 'penalties/penalty_form.html'
    success_url = reverse_lazy('penalties:list')
    success_message = "Penalty updated."


class PenaltyDeleteView(AdminRequiredMixin, DeleteView):
    model = Penalty
    template_name = 'penalties/penalty_confirm_delete.html'
    success_url = reverse_lazy('penalties:list')


class PenaltyMarkPaidView(TreasurerRequiredMixin, View):
    def post(self, request, pk):
        penalty = get_object_or_404(Penalty, pk=pk)
        penalty.paid = True
        penalty.paid_date = timezone.localdate()
        penalty.save()
        messages.success(request, f"Penalty of KES {penalty.amount} for {penalty.member.name} marked as paid.")
        # Only redirect to safe internal URLs — never follow user-supplied next param to external sites
        next_url = request.POST.get('next', '')
        if next_url and next_url.startswith('/') and not next_url.startswith('//'):
            return redirect(next_url)
        return redirect('penalties:list')


class PenaltyExportView(MemberAccessMixin, View):
    def get(self, request):
        format_type = request.GET.get('format', 'csv')
        qs = Penalty.objects.select_related('member')
        q = request.GET.get('q', '').strip()
        paid = request.GET.get('paid', '').strip()
        if q:
            qs = qs.filter(member__name__icontains=q)
        if paid == '1':
            qs = qs.filter(paid=True)
        elif paid == '0':
            qs = qs.filter(paid=False)

        fields = [
            ('member.name', 'Member'),
            ('amount', 'Amount (KES)'),
            ('date', 'Date'),
            ('reason', 'Reason'),
            (lambda obj: 'Yes' if obj.paid else 'No', 'Paid'),
            ('paid_date', 'Paid Date'),
        ]
        if format_type == 'pdf':
            return export_pdf(qs, 'penalties', 'Penalties Report', fields, orientation='landscape')
        return export_csv(qs, 'penalties', fields)