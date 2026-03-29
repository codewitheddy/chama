from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.urls import reverse_lazy
from django.db import models
from django.contrib import messages
from django.shortcuts import redirect
import csv
import io
from .models import Member
from .forms import MemberForm
from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin


class MemberListView(LoginRequiredMixin, ListView):
    model = Member
    template_name = 'members/member_list.html'
    context_object_name = 'members'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(models.Q(name__icontains=q) | models.Q(phone__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class MemberCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = Member
    form_class = MemberForm
    template_name = 'members/member_form.html'
    success_url = reverse_lazy('members:list')
    success_message = "Member added successfully."


class MemberUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Member
    form_class = MemberForm
    template_name = 'members/member_form.html'
    success_url = reverse_lazy('members:list')
    success_message = "Member updated successfully."


class MemberDeleteView(AdminRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Member
    template_name = 'members/member_confirm_delete.html'
    success_url = reverse_lazy('members:list')
    success_message = "Member deleted."


class MemberDetailView(LoginRequiredMixin, DetailView):
    model = Member
    template_name = 'members/member_detail.html'
    context_object_name = 'member'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['contributions'] = self.object.contribution_set.all()
        ctx['loans'] = self.object.loan_set.all()
        ctx['payments'] = self.object.payment_set.all()
        penalties = self.object.penalties.all()
        ctx['penalties'] = penalties
        from django.db.models import Sum
        ctx['total_penalties_issued'] = penalties.aggregate(t=Sum('amount'))['t'] or 0
        ctx['total_penalties_paid'] = penalties.filter(paid=True).aggregate(t=Sum('amount'))['t'] or 0
        ctx['total_penalties_outstanding'] = penalties.filter(paid=False).aggregate(t=Sum('amount'))['t'] or 0
        from loans.models import LoanGuarantor
        ctx['guarantees'] = LoanGuarantor.objects.filter(
            guarantor=self.object
        ).select_related('loan__member')
        return ctx


class MemberImportView(TreasurerRequiredMixin, TemplateView):
    template_name = 'members/member_import.html'

    def post(self, request, *args, **kwargs):
        csv_file = request.FILES.get('csv_file')
        if not csv_file or not csv_file.name.endswith('.csv'):
            messages.error(request, "Please upload a valid .csv file.")
            return redirect('members:import')

        decoded = csv_file.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(decoded))
        created, skipped, errors = 0, 0, []

        for i, row in enumerate(reader, start=2):
            name = row.get('name', '').strip()
            phone = row.get('phone', '').strip()
            reg_fee = row.get('registration_fee', '0').strip() or '0'
            if not name:
                errors.append(f"Row {i}: name is required.")
                continue
            if Member.objects.filter(phone=phone).exists():
                skipped += 1
                continue
            try:
                Member.objects.create(name=name, phone=phone, registration_fee=reg_fee)
                created += 1
            except Exception as e:
                errors.append(f"Row {i}: {e}")

        if created:
            messages.success(request, f"{created} member(s) imported successfully.")
        if skipped:
            messages.warning(request, f"{skipped} row(s) skipped (duplicate phone).")
        for err in errors:
            messages.error(request, err)

        return redirect('members:list')
