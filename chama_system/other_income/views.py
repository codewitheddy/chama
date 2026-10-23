from decimal import Decimal
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, View
from django.urls import reverse_lazy
from django.db import transaction
from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from .models import OtherIncome
from .forms import OtherIncomeForm
from bank_accounts.models import BankAccount
from accounts.mixins import (
    TreasurerRequiredMixin,
    AdminRequiredMixin,
    MemberAccessMixin,
    AdminPasswordDeleteMixin,
)


class OtherIncomeListView(MemberAccessMixin, ListView):
    model = OtherIncome
    template_name = 'other_income/list.html'
    context_object_name = 'incomes'
    paginate_by = 20

    def get_queryset(self):
        qs = OtherIncome.objects.select_related('bank_account', 'recorded_by', 'reconciled_by').all()

        q = self.request.GET.get('q', '').strip()
        payment_method = self.request.GET.get('payment_method', '').strip()
        bank_account_id = self.request.GET.get('bank_account', '').strip()
        category = self.request.GET.get('category', '').strip()
        reconciled = self.request.GET.get('reconciled', '').strip()

        if q:
            qs = qs.filter(
                Q(source__icontains=q) |
                Q(reference_number__icontains=q) |
                Q(description__icontains=q)
            )
        if payment_method:
            qs = qs.filter(payment_method=payment_method)
        if bank_account_id:
            qs = qs.filter(bank_account_id=bank_account_id)
        if category:
            qs = qs.filter(category=category)
        if reconciled == 'yes':
            qs = qs.filter(is_reconciled=True)
        elif reconciled == 'no':
            qs = qs.filter(is_reconciled=False)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from utils.financials import get_available_fund_balance

        all_incomes = OtherIncome.objects.all()

        ctx['total_other_income'] = all_incomes.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        ctx['total_bank_transfer'] = all_incomes.filter(
            payment_method__in=[OtherIncome.PAYMENT_BANK_TRANSFER, OtherIncome.PAYMENT_CHEQUE]
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        ctx['total_cash'] = all_incomes.filter(
            payment_method=OtherIncome.PAYMENT_CASH
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        ctx['total_mpesa'] = all_incomes.filter(
            payment_method=OtherIncome.PAYMENT_MPESA
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        ctx['total_reconciled'] = all_incomes.filter(is_reconciled=True).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        ctx['total_unreconciled'] = all_incomes.filter(is_reconciled=False).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        ctx['unreconciled_count'] = all_incomes.filter(is_reconciled=False).count()

        ctx['available_fund_balance'] = get_available_fund_balance()
        ctx['income_count'] = all_incomes.count()

        # Filter choices
        ctx['bank_accounts'] = BankAccount.objects.filter(is_active=True)
        ctx['categories'] = OtherIncome.CATEGORY_CHOICES
        ctx['payment_methods'] = OtherIncome.PAYMENT_METHOD_CHOICES

        # Current filter params
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_payment_method'] = self.request.GET.get('payment_method', '')
        ctx['selected_bank_account'] = self.request.GET.get('bank_account', '')
        ctx['selected_category'] = self.request.GET.get('category', '')
        ctx['selected_reconciled'] = self.request.GET.get('reconciled', '')

        return ctx


class OtherIncomeCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = OtherIncome
    form_class = OtherIncomeForm
    template_name = 'other_income/form.html'
    success_url = reverse_lazy('other_income:list')
    success_message = "Other income record added and accounts updated successfully."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from utils.financials import get_available_fund_balance
        ctx['available_fund_balance'] = get_available_fund_balance()
        ctx['total_other_income'] = OtherIncome.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        ctx['income_count'] = OtherIncome.objects.count()
        ctx['recent_incomes'] = OtherIncome.objects.select_related('bank_account').order_by('-date', '-created_at')[:5]
        ctx['bank_accounts'] = BankAccount.objects.filter(is_active=True)
        return ctx

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.recorded_by = self.request.user
            response = super().form_valid(form)
            self.object.sync_bank_ledger()
            return response


class OtherIncomeUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = OtherIncome
    form_class = OtherIncomeForm
    template_name = 'other_income/form.html'
    success_url = reverse_lazy('other_income:list')
    success_message = "Income record and affected accounts updated successfully."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from utils.financials import get_available_fund_balance
        ctx['available_fund_balance'] = get_available_fund_balance()
        ctx['total_other_income'] = OtherIncome.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        ctx['income_count'] = OtherIncome.objects.count()
        ctx['recent_incomes'] = OtherIncome.objects.select_related('bank_account').order_by('-date', '-created_at')[:5]
        ctx['bank_accounts'] = BankAccount.objects.filter(is_active=True)
        return ctx

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            self.object.sync_bank_ledger()
            return response


class OtherIncomeDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = OtherIncome
    template_name = 'other_income/confirm_delete.html'
    success_url = reverse_lazy('other_income:list')

    def delete(self, request, *args, **kwargs):
        income = self.get_object()
        source_name = income.source
        amount_fmt = f"KES {income.amount:,.2f}"
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f"Other income entry '{source_name}' ({amount_fmt}) deleted and bank accounts adjusted.")
        return response


class OtherIncomeReconcileToggleView(TreasurerRequiredMixin, View):
    """
    Allows treasurer/admin to toggle reconciliation verification on an income entry.
    """
    def post(self, request, pk):
        income = get_object_or_404(OtherIncome, pk=pk)
        if income.is_reconciled:
            income.is_reconciled = False
            income.reconciled_date = None
            income.reconciled_by = None
            income.reconciliation_notes = ''
            income.save(update_fields=['is_reconciled', 'reconciled_date', 'reconciled_by', 'reconciliation_notes'])
            messages.info(request, f"Income #{income.pk} ({income.source}) marked as Pending Reconciliation.")
        else:
            income.is_reconciled = True
            income.reconciled_date = timezone.localdate()
            income.reconciled_by = request.user
            notes = request.POST.get('reconciliation_notes', '').strip()
            if notes:
                income.reconciliation_notes = notes
            income.save(update_fields=['is_reconciled', 'reconciled_date', 'reconciled_by', 'reconciliation_notes'])
            messages.success(
                request,
                f"Income #{income.pk} ({income.source}) successfully marked Reconciled & Verified by {request.user.get_full_name() or request.user.username}."
            )

        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse_lazy('other_income:list')
        return redirect(next_url)
