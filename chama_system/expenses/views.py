from decimal import Decimal

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, View

from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin, MemberAccessMixin, AdminPasswordDeleteMixin
from utils.exports import export_csv, export_pdf
from utils.financials import get_available_fund_balance, get_registration_fee_balance
from .models import Expense, ExpenseCategory
from .forms import ExpenseForm, ExpenseCategoryForm
from members.models import RegistrationFeeRate, Member


# ── Expense Category Views (Admin only) ───────────────────────────────────────

class ExpenseCategoryListView(AdminRequiredMixin, ListView):
    model = ExpenseCategory
    template_name = 'expenses/category_list.html'
    context_object_name = 'categories'

    def get_queryset(self):
        from django.db.models import Count
        return ExpenseCategory.objects.annotate(expense_count=Count('expenses'))


class ExpenseCategoryCreateView(AdminRequiredMixin, SuccessMessageMixin, CreateView):
    model = ExpenseCategory
    form_class = ExpenseCategoryForm
    template_name = 'expenses/category_form.html'
    success_url = reverse_lazy('expenses:category_list')
    success_message = "Category '%(name)s' created."


class ExpenseCategoryUpdateView(AdminRequiredMixin, SuccessMessageMixin, UpdateView):
    model = ExpenseCategory
    form_class = ExpenseCategoryForm
    template_name = 'expenses/category_form.html'
    success_url = reverse_lazy('expenses:category_list')
    success_message = "Category updated."


class ExpenseCategoryDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = ExpenseCategory
    template_name = 'expenses/category_confirm_delete.html'
    success_url = reverse_lazy('expenses:category_list')

    def post(self, request, *args, **kwargs):
        cat = self.get_object()
        if cat.expenses.exists():
            messages.error(
                request,
                f'Cannot delete "{cat.name}" — it has {cat.expenses.count()} expense(s) recorded against it. '
                'Deactivate it instead.'
            )
            return redirect('expenses:category_list')
        response = super().post(request, *args, **kwargs)
        if response.status_code == 302:
            messages.success(request, f'Category "{cat.name}" deleted.')
        return response


# ── Expense Views ─────────────────────────────────────────────────────────────

class ExpenseListView(MemberAccessMixin, ListView):
    model = Expense
    template_name = 'expenses/expense_list.html'
    context_object_name = 'expenses'
    paginate_by = 25

    def get_queryset(self):
        qs = Expense.objects.select_related('category', 'fund_source_bank', 'recorded_by')
        q      = self.request.GET.get('q', '').strip()
        source = self.request.GET.get('source', '').strip()
        cat    = self.request.GET.get('cat', '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(description__icontains=q) | Q(category__name__icontains=q))
        if source:
            qs = qs.filter(fund_source=source)
        if cat:
            qs = qs.filter(category_id=cat)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from django.db.models import Sum
        ctx['total_expenses']      = Expense.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        ctx['q']                   = self.request.GET.get('q', '')
        ctx['selected_source']     = self.request.GET.get('source', '')
        ctx['selected_cat']        = self.request.GET.get('cat', '')
        ctx['fund_source_choices'] = Expense.FUND_SOURCE_CHOICES
        ctx['categories']          = ExpenseCategory.objects.filter(is_active=True)
        return ctx


class ExpenseCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/expense_form.html'
    success_url = reverse_lazy('expenses:list')
    success_message = "Expense recorded successfully."

    def dispatch(self, request, *args, **kwargs):
        # Gate: block if no active categories exist
        if not ExpenseCategory.objects.filter(is_active=True).exists():
            messages.error(
                request,
                'No expense categories have been set up yet. '
                'An admin must create at least one category before recording expenses.'
            )
            return redirect('expenses:list')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['available_fund_balance']  = get_available_fund_balance()
        ctx['reg_fee_balance']         = get_registration_fee_balance()
        try:
            from bank_accounts.models import BankAccount
            ctx['bank_accounts'] = BankAccount.objects.filter(is_active=True)
        except Exception:
            ctx['bank_accounts'] = []
        return ctx

    def form_valid(self, form):
        amount      = form.cleaned_data.get('amount')
        fund_source = form.cleaned_data.get('fund_source', 'group_funds')
        bank        = form.cleaned_data.get('fund_source_bank')

        # ── Balance check BEFORE saving ───────────────────────────
        if fund_source == 'group_funds':
            available = get_available_fund_balance()
            if amount and amount > available:
                messages.error(
                    self.request,
                    f'Expense of KES {amount:,.2f} exceeds the available group fund balance '
                    f'of KES {available:,.2f}.'
                )
                return self.form_invalid(form)

        elif fund_source == 'registration_fees':
            reg_bal = get_registration_fee_balance()
            if amount and amount > reg_bal:
                messages.error(
                    self.request,
                    f'Expense of KES {amount:,.2f} exceeds the available registration fee '
                    f'fund balance of KES {reg_bal:,.2f}.'
                )
                return self.form_invalid(form)

        elif fund_source == 'bank_account':
            if not bank:
                messages.error(self.request, 'Please select a bank account.')
                return self.form_invalid(form)
            bank_bal = bank.current_balance
            if amount and amount > bank_bal:
                messages.error(
                    self.request,
                    f'Expense of KES {amount:,.2f} exceeds the {bank.bank_name} '
                    f'balance of KES {bank_bal:,.2f}.'
                )
                return self.form_invalid(form)

        with transaction.atomic():
            form.instance.recorded_by = self.request.user
            response = super().form_valid(form)
            expense = self.object

            # ── Deduct from bank account ──────────────────────────
            if expense.fund_source == 'bank_account' and expense.fund_source_bank:
                from bank_accounts.models import BankBalance
                from django.utils import timezone
                bank_account = expense.fund_source_bank
                current_bal  = bank_account.current_balance
                new_bal      = current_bal - expense.amount
                if new_bal < Decimal('0'):
                    transaction.set_rollback(True)
                    messages.error(
                        self.request,
                        f'Insufficient bank balance. {bank_account.bank_name} has '
                        f'KES {current_bal:,.2f} but expense requires KES {expense.amount:,.2f}.'
                    )
                    return self.form_invalid(form)
                BankBalance.objects.create(
                    account=bank_account,
                    balance=new_bal,
                    topup_amount=expense.amount,
                    transaction_type=BankBalance.TYPE_DEDUCTION,
                    recorded_on=timezone.localdate(),
                    notes=f'Expense for {expense.category.name}: {expense.description} — '
                          f'KES {expense.amount:,.2f} deducted. Expense #{expense.pk}.',
                    recorded_by=self.request.user,
                )

        return response


class ExpenseUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/expense_form.html'
    success_url = reverse_lazy('expenses:list')
    success_message = "Expense updated."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['available_fund_balance'] = get_available_fund_balance()
        ctx['reg_fee_balance']        = get_registration_fee_balance()
        try:
            from bank_accounts.models import BankAccount
            ctx['bank_accounts'] = BankAccount.objects.filter(is_active=True)
        except Exception:
            ctx['bank_accounts'] = []
        return ctx


class ExpenseDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = Expense
    template_name = 'expenses/expense_confirm_delete.html'
    success_url = reverse_lazy('expenses:list')


class ExpenseDetailView(MemberAccessMixin, DetailView):
    model = Expense
    template_name = 'expenses/expense_detail.html'
    context_object_name = 'expense'


class ExpenseExportView(MemberAccessMixin, View):
    def get(self, request):
        format_type = request.GET.get('format', 'csv')
        qs = Expense.objects.select_related('category', 'fund_source_bank').order_by('-date')
        fields = [
            ('date', 'Date'),
            (lambda obj: obj.category.name, 'Category'),
            ('description', 'Description'),
            ('amount', 'Amount (KES)'),
            (lambda obj: obj.fund_source_description, 'Fund Source'),
            ('receipt_number', 'Receipt #'),
            ('notes', 'Notes'),
        ]
        if format_type == 'pdf':
            return export_pdf(qs, 'expenses', 'Expenses Report', fields, orientation='landscape')
        return export_csv(qs, 'expenses', fields)


class RegistrationFeeFundView(MemberAccessMixin, View):
    """
    Registration Fee Fund dashboard.
    Shows the total collected, total spent, available balance,
    per-member breakdown (paginated + searchable + status filtered), and spending history.
    """
    template_name = 'expenses/reg_fee_fund.html'

    def get(self, request):
        from django.db.models import Sum, Q
        from django.core.paginator import Paginator
        from members.models import Member, RegistrationFeeRate

        q = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status', '').strip()

        # Inflows — members list with filters
        members_qs = Member.objects.all().order_by('-date_joined', 'name')

        if q:
            members_qs = members_qs.filter(
                Q(name__icontains=q) | Q(phone__icontains=q)
            )

        if status_filter == 'paid':
            members_qs = members_qs.filter(registration_fee_paid__gt=0)
        elif status_filter == 'unpaid':
            members_qs = members_qs.filter(registration_fee_paid=0)

        # Actual collected amount across all members
        all_members = Member.objects.all()
        total_collected = all_members.aggregate(t=Sum('registration_fee_paid'))['t'] or Decimal('0')
        active_members_count = all_members.filter(is_active=True).count()
        paid_members_count = all_members.filter(is_active=True, registration_fee_paid__gt=0).count()
        unpaid_members_count = all_members.filter(is_active=True, registration_fee_paid=0).count()

        collection_pct = (paid_members_count / active_members_count * 100) if active_members_count > 0 else 0

        # Paginate member list
        paginator = Paginator(members_qs, 15)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # Outflows
        reg_fee_expenses = Expense.objects.filter(
            fund_source='registration_fees'
        ).select_related('category').order_by('-date')

        total_spent = reg_fee_expenses.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        available_balance = max(total_collected - total_spent, Decimal('0'))

        current_rate = RegistrationFeeRate.current_rate()

        return render(request, self.template_name, {
            'page_obj': page_obj,
            'q': q,
            'status_filter': status_filter,
            'total_collected': total_collected,
            'total_spent': total_spent,
            'available_balance': available_balance,
            'reg_fee_expenses': reg_fee_expenses,
            'member_count': members_qs.count(),
            'active_members_count': active_members_count,
            'paid_members_count': paid_members_count,
            'unpaid_members_count': unpaid_members_count,
            'collection_pct': round(collection_pct, 1),
            'current_rate': current_rate,
        })


class RegistrationFeeFundExportView(MemberAccessMixin, View):
    """Export member registration fee list or registration fee expenses."""
    def get(self, request):
        return self._export(request)

    def post(self, request):
        return self._export(request)

    def _export(self, request):
        fmt = request.GET.get('format') or request.POST.get('format', 'csv')
        export_type = request.GET.get('type') or request.POST.get('type', 'members')
        raw_ids = request.GET.get('ids') or request.POST.get('ids', '')

        if export_type == 'expenses':
            qs = Expense.objects.filter(fund_source='registration_fees').select_related('category').order_by('-date')
            fields = [
                ('date', 'Date'),
                (lambda obj: obj.category.name if obj.category else 'General', 'Category'),
                ('description', 'Description'),
                ('amount', 'Amount (KES)'),
                ('receipt_number', 'Receipt #'),
                ('notes', 'Notes'),
            ]
            title = 'Registration Fee Fund - Spending History'
            if fmt == 'pdf':
                return export_pdf(qs, 'reg_fee_fund_expenses', title, fields, orientation='landscape')
            return export_csv(qs, 'reg_fee_fund_expenses', fields)
        else:
            qs = Member.objects.all().order_by('-date_joined', 'name')
            if raw_ids:
                id_list = [int(i) for i in raw_ids.split(',') if i.strip().isdigit()]
                if id_list:
                    qs = qs.filter(pk__in=id_list)
            else:
                q = request.GET.get('q', '').strip()
                status_filter = request.GET.get('status', '').strip()
                if q:
                    qs = qs.filter(name__icontains=q)
                if status_filter == 'paid':
                    qs = qs.filter(registration_fee_paid__gt=0)
                elif status_filter == 'unpaid':
                    qs = qs.filter(registration_fee_paid=0)

            fields = [
                ('name', 'Member Name'),
                ('phone', 'Phone Number'),
                (lambda obj: 'Active' if obj.is_active else 'Exited', 'Status'),
                ('date_joined', 'Date Joined'),
                ('registration_fee_paid', 'Registration Fee Paid (KES)'),
            ]
            title = 'Registration Fee Fund - Member Fees Report'
            if fmt == 'pdf':
                return export_pdf(qs, 'reg_fee_members_report', title, fields, orientation='landscape')
            return export_csv(qs, 'reg_fee_members_report', fields)

