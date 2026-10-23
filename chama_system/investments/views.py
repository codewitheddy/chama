from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .models import Investment, InvestmentValuation, InvestmentReturn, InvestmentWithdrawal, InvestmentType, InvestmentCategory
from .forms import InvestmentForm, InvestmentValuationForm, InvestmentReturnForm, InvestmentWithdrawalForm, InvestmentTypeForm, InvestmentCategoryForm
from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin, MemberAccessMixin, AdminPasswordDeleteMixin


class InvestmentListView(MemberAccessMixin, ListView):
    """List all investments with summary statistics."""
    model = Investment
    template_name = 'investments/list.html'
    context_object_name = 'investments'
    paginate_by = 20

    def get_queryset(self):
        qs = Investment.objects.select_related(
            'investment_type__category', 'fund_source_bank', 'recorded_by', 'approved_by'
        ).prefetch_related('valuations', 'returns', 'withdrawals')
        
        status = self.request.GET.get('status', '')
        fund_source = self.request.GET.get('fund_source', '')
        category_id = self.request.GET.get('category', '')
        q = self.request.GET.get('q', '').strip()
        
        if status:
            qs = qs.filter(status=status)
        if fund_source:
            qs = qs.filter(fund_source=fund_source)
        if category_id:
            qs = qs.filter(investment_type__category_id=category_id)
        if q:
            qs = qs.filter(
                Q(investment_type__name__icontains=q) |
                Q(description__icontains=q) |
                Q(certificate_number__icontains=q) |
                Q(investment_type__category__name__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        all_investments = Investment.objects.all()
        
        ctx['total_invested'] = all_investments.aggregate(t=Sum('initial_amount'))['t'] or 0
        ctx['total_current_value'] = sum(inv.current_value for inv in all_investments)
        ctx['total_returns'] = all_investments.aggregate(t=Sum('returns__amount'))['t'] or 0
        ctx['total_withdrawn'] = all_investments.aggregate(t=Sum('withdrawals__amount_received'))['t'] or 0
        ctx['net_position'] = ctx['total_current_value'] + ctx['total_returns'] - ctx['total_invested']
        ctx['active_count'] = all_investments.filter(status='active').count()
        
        ctx['status'] = self.request.GET.get('status', '')
        ctx['fund_source'] = self.request.GET.get('fund_source', '')
        ctx['category_id'] = self.request.GET.get('category', '')
        ctx['q'] = self.request.GET.get('q', '')
        ctx['statuses'] = dict(Investment.STATUS_CHOICES)
        ctx['fund_sources'] = dict(Investment.FUND_SOURCE_CHOICES)
        ctx['categories'] = InvestmentCategory.objects.all().order_by('display_order', 'name')
        
        return ctx


class InvestmentDetailView(MemberAccessMixin, DetailView):
    """Detailed view of a single investment with valuations, returns, and withdrawals."""
    model = Investment
    template_name = 'investments/detail.html'
    context_object_name = 'investment'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        investment = self.get_object()
        
        ctx['valuations'] = investment.valuations.all()
        ctx['returns'] = investment.returns.all()
        ctx['withdrawals'] = investment.withdrawals.all()
        ctx['gain_loss'] = investment.net_gain_loss
        ctx['roi'] = investment.roi_percentage
        
        return ctx


class InvestmentCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    """Record a new investment purchase."""
    model = Investment
    form_class = InvestmentForm
    template_name = 'investments/form.html'
    success_url = reverse_lazy('investments:list')
    success_message = "Investment recorded successfully. Funds will be deducted upon approval."

    def form_valid(self, form):
        form.instance.recorded_by = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action'] = 'Add Investment'
        from utils.financials import get_available_fund_balance
        from bank_accounts.models import BankAccount
        ctx['group_fund_balance'] = get_available_fund_balance()
        ctx['bank_accounts'] = BankAccount.objects.filter(is_active=True)
        return ctx


class InvestmentUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    """Edit an existing investment record."""
    model = Investment
    form_class = InvestmentForm
    template_name = 'investments/form.html'
    success_url = reverse_lazy('investments:list')
    success_message = "Investment updated successfully."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action'] = 'Edit Investment'
        from utils.financials import get_available_fund_balance
        from bank_accounts.models import BankAccount
        ctx['group_fund_balance'] = get_available_fund_balance()
        ctx['bank_accounts'] = BankAccount.objects.filter(is_active=True)
        return ctx


class InvestmentDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    """Delete an investment (requires admin password)."""
    model = Investment
    template_name = 'investments/confirm_delete.html'
    success_url = reverse_lazy('investments:list')


class InvestmentApprovalView(AdminRequiredMixin, View):
    """
    Approve an investment and deduct funds from the selected source.
    Uses atomic transaction with select_for_update() to prevent concurrent approvals.
    """
    def post(self, request, pk):
        from django.db import transaction
        from django.contrib import messages
        from django.utils import timezone
        from bank_accounts.models import BankBalance
        from utils.financials import get_available_fund_balance

        investment = get_object_or_404(Investment, pk=pk)

        # Prevent double approval
        if investment.funds_deducted:
            messages.error(request, 'Investment has already been approved and funds deducted.')
            return redirect('investments:detail', pk=pk)

        try:
            with transaction.atomic():
                # Lock the investment record to prevent concurrent approvals
                investment = Investment.objects.select_for_update().get(pk=pk)

                # Double-check again after lock acquired
                if investment.funds_deducted:
                    messages.warning(request, 'Investment was approved by another user.')
                    return redirect('investments:detail', pk=pk)

                # ── Validate funds availability (latest balance from DB) ──────────────
                if investment.fund_source == 'group_funds':
                    available = get_available_fund_balance()
                    if investment.initial_amount > available:
                        messages.error(
                            request,
                            f'Cannot approve investment: KES {investment.initial_amount:,.2f} exceeds '
                            f'available group fund balance of KES {available:,.2f}.'
                        )
                        transaction.set_rollback(True)
                        return redirect('investments:detail', pk=pk)

                    # ── Deduct from group funds via Expense record ────────────────
                    from expenses.models import Expense, ExpenseCategory
                    inv_category, _ = ExpenseCategory.objects.get_or_create(
                        name='Investment',
                        defaults={'description': 'Funds allocated to group investments.'},
                    )
                    Expense.objects.create(
                        category=inv_category,
                        description=(
                            f'Investment: {investment.investment_type.name} '
                            f'(#{investment.pk})'
                        ),
                        amount=investment.initial_amount,
                        date=investment.date_invested or timezone.localdate(),
                        fund_source='group_funds',
                        notes=(
                            f'Auto-created on approval of investment #{investment.pk}. '
                            f'Approved by {request.user.username}.'
                        ),
                        recorded_by=request.user,
                    )

                elif investment.fund_source in ('bank_account', 'bank_transfer'):
                    if investment.fund_source_bank:
                        # Lock the bank account to prevent simultaneous withdrawals
                        bank = investment.fund_source_bank.__class__.objects.select_for_update().get(
                            pk=investment.fund_source_bank.pk
                        )
                        current_bal = bank.current_balance
                        if investment.initial_amount > current_bal:
                            messages.error(
                                request,
                                f'Cannot approve investment: KES {investment.initial_amount:,.2f} exceeds '
                                f'{bank.bank_name} balance of KES {current_bal:,.2f}.'
                            )
                            transaction.set_rollback(True)
                            return redirect('investments:detail', pk=pk)

                        # ── Deduct from bank account ──────────────────────────────────
                        new_bal = current_bal - investment.initial_amount
                        BankBalance.objects.create(
                            account=bank,
                            balance=new_bal,
                            topup_amount=investment.initial_amount,
                            transaction_type=BankBalance.TYPE_DEDUCTION,
                            recorded_on=timezone.localdate(),
                            notes=(
                                f'Investment {investment.investment_type.name} (KES {investment.initial_amount:,.2f}) '
                                f'approved and deducted via {investment.get_fund_source_display()}. Investment #{investment.pk}.'
                            ),
                            recorded_by=request.user,
                        )
                    elif investment.fund_source == 'bank_account':
                        messages.error(request, 'Bank account not set for this investment.')
                        transaction.set_rollback(True)
                        return redirect('investments:detail', pk=pk)

                # ── Mark as approved and deducted ─────────────────────────────────
                investment.funds_deducted = True
                investment.approved_by = request.user
                investment.approved_at = timezone.now()
                investment.save(update_fields=['funds_deducted', 'approved_by', 'approved_at'])

                messages.success(
                    request,
                    f'Investment of KES {investment.initial_amount:,.2f} approved and funds deducted.'
                )

        except Exception as e:
            messages.error(request, f'Error approving investment: {str(e)}')
            return redirect('investments:detail', pk=pk)

        return redirect('investments:detail', pk=pk)


class InvestmentValuationView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    """Record a new valuation for an investment."""
    model = InvestmentValuation
    form_class = InvestmentValuationForm
    template_name = 'investments/valuation_form.html'
    success_message = "Valuation recorded successfully."

    def dispatch(self, request, *args, **kwargs):
        self.investment = get_object_or_404(Investment, pk=kwargs['investment_pk'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.investment = self.investment
        form.instance.valuation_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('investments:detail', kwargs={'pk': self.investment.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['investment'] = self.investment
        return ctx


class InvestmentReturnView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    """Record a return/dividend/interest from an investment."""
    model = InvestmentReturn
    form_class = InvestmentReturnForm
    template_name = 'investments/return_form.html'
    success_message = "Return recorded successfully."

    def dispatch(self, request, *args, **kwargs):
        self.investment = get_object_or_404(Investment, pk=kwargs['investment_pk'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.investment = self.investment
        form.instance.recorded_by = self.request.user
        response = super().form_valid(form)
        ret = self.object

        from django.utils import timezone
        from bank_accounts.models import BankBalance
        from other_income.models import OtherIncome

        if ret.payment_type == 'bank_transfer' and ret.bank_account:
            curr = ret.bank_account.current_balance
            BankBalance.objects.create(
                account=ret.bank_account,
                balance=curr + ret.amount,
                topup_amount=ret.amount,
                transaction_type=BankBalance.TYPE_TOPUP,
                recorded_on=ret.return_date or timezone.localdate(),
                notes=f"Investment return from {self.investment.investment_type.name} (Return #{ret.pk})",
                recorded_by=self.request.user,
            )

        OtherIncome.objects.create(
            source=f"Investment Return: {self.investment.investment_type.name}",
            amount=ret.amount,
            date=ret.return_date or timezone.localdate(),
            description=f"Return #{ret.pk} ({ret.get_return_type_display()}) from {self.investment}. {ret.description}".strip(),
        )

        return response

    def get_success_url(self):
        return reverse_lazy('investments:detail', kwargs={'pk': self.investment.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['investment'] = self.investment
        return ctx


class InvestmentWithdrawalView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    """Record a withdrawal/liquidation of an investment."""
    model = InvestmentWithdrawal
    form_class = InvestmentWithdrawalForm
    template_name = 'investments/withdrawal_form.html'
    success_message = "Withdrawal recorded successfully."

    def dispatch(self, request, *args, **kwargs):
        self.investment = get_object_or_404(Investment, pk=kwargs['investment_pk'])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.investment = self.investment
        form.instance.recorded_by = self.request.user
        
        # If full liquidation, mark investment as completed
        if form.instance.withdrawal_type == 'full':
            self.investment.status = 'completed'
            self.investment.save()
        
        response = super().form_valid(form)
        w = self.object

        from django.utils import timezone
        from bank_accounts.models import BankBalance
        from other_income.models import OtherIncome

        if w.payment_type == 'bank_transfer' and w.bank_account:
            curr = w.bank_account.current_balance
            BankBalance.objects.create(
                account=w.bank_account,
                balance=curr + w.amount_received,
                topup_amount=w.amount_received,
                transaction_type=BankBalance.TYPE_TOPUP,
                recorded_on=w.withdrawal_date or timezone.localdate(),
                notes=f"Investment withdrawal from {self.investment.investment_type.name} (Withdrawal #{w.pk})",
                recorded_by=self.request.user,
            )

        if w.payment_type in ('cash', 'mpesa'):
            OtherIncome.objects.create(
                source=f"Investment Liquidation: {self.investment.investment_type.name}",
                amount=w.amount_received,
                date=w.withdrawal_date or timezone.localdate(),
                description=f"Withdrawal #{w.pk} ({w.get_withdrawal_type_display()}) from {self.investment}.",
            )

        return response

    def get_success_url(self):
        return reverse_lazy('investments:detail', kwargs={'pk': self.investment.pk})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['investment'] = self.investment
        return ctx


class InvestmentReturnDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    """Delete an investment return record."""
    model = InvestmentReturn
    template_name = 'investments/return_confirm_delete.html'

    def get_success_url(self):
        return reverse_lazy('investments:detail', kwargs={'pk': self.object.investment.pk})


class InvestmentValuationDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    """Delete an investment valuation record."""
    model = InvestmentValuation
    template_name = 'investments/valuation_confirm_delete.html'

    def get_success_url(self):
        return reverse_lazy('investments:detail', kwargs={'pk': self.object.investment.pk})


class InvestmentWithdrawalDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    """Delete an investment withdrawal record."""
    model = InvestmentWithdrawal
    template_name = 'investments/withdrawal_confirm_delete.html'

    def get_success_url(self):
        return reverse_lazy('investments:detail', kwargs={'pk': self.object.investment.pk})


# ─── Investment Type Management ───────────────────────────────────────────


class InvestmentTypeListView(AdminRequiredMixin, ListView):
    """List all investment types."""
    model = InvestmentType
    template_name = 'investments/type_list.html'
    context_object_name = 'types'
    paginate_by = 20

    def get_queryset(self):
        qs = InvestmentType.objects.select_related('category').prefetch_related('investments').all()
        q = self.request.GET.get('q', '').strip()
        category_id = self.request.GET.get('category', '').strip()
        status = self.request.GET.get('status', '').strip()

        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(category__name__icontains=q))
        if category_id:
            qs = qs.filter(category_id=category_id)
        if status == 'active':
            qs = qs.filter(is_active=True)
        elif status == 'inactive':
            qs = qs.filter(is_active=False)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        all_types = InvestmentType.objects.all()
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_category'] = self.request.GET.get('category', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['categories'] = InvestmentCategory.objects.all()
        ctx['total_types'] = all_types.count()
        ctx['active_types'] = all_types.filter(is_active=True).count()
        ctx['inactive_types'] = all_types.filter(is_active=False).count()
        ctx['total_categories'] = InvestmentCategory.objects.count()
        return ctx


class InvestmentTypeCreateView(AdminRequiredMixin, SuccessMessageMixin, CreateView):
    """Create a new investment type."""
    model = InvestmentType
    form_class = InvestmentTypeForm
    template_name = 'investments/type_form.html'
    success_url = reverse_lazy('investments:type_list')
    success_message = "Investment type created successfully."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action'] = 'Add Investment Type'
        return ctx


class InvestmentTypeUpdateView(AdminRequiredMixin, SuccessMessageMixin, UpdateView):
    """Edit an existing investment type."""
    model = InvestmentType
    form_class = InvestmentTypeForm
    template_name = 'investments/type_form.html'
    success_url = reverse_lazy('investments:type_list')
    success_message = "Investment type updated successfully."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action'] = 'Edit Investment Type'
        return ctx


class InvestmentTypeDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    """Delete an investment type."""
    model = InvestmentType
    template_name = 'investments/type_confirm_delete.html'
    success_url = reverse_lazy('investments:type_list')


# ─── Investment Category Management ───────────────────────────────────────


class InvestmentCategoryListView(AdminRequiredMixin, ListView):
    """List all investment categories."""
    model = InvestmentCategory
    template_name = 'investments/category_list.html'
    context_object_name = 'categories'
    paginate_by = 20

    def get_queryset(self):
        qs = InvestmentCategory.objects.all()
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class InvestmentCategoryCreateView(AdminRequiredMixin, SuccessMessageMixin, CreateView):
    """Create a new investment category."""
    model = InvestmentCategory
    form_class = InvestmentCategoryForm
    template_name = 'investments/category_form.html'
    success_url = reverse_lazy('investments:category_list')
    success_message = "Investment category created successfully."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action'] = 'Add Investment Category'
        ctx['linked_types'] = []
        ctx['total_linked_types'] = 0
        return ctx


class InvestmentCategoryUpdateView(AdminRequiredMixin, SuccessMessageMixin, UpdateView):
    """Edit an existing investment category."""
    model = InvestmentCategory
    form_class = InvestmentCategoryForm
    template_name = 'investments/category_form.html'
    success_url = reverse_lazy('investments:category_list')
    success_message = "Investment category updated successfully."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['action'] = 'Edit Investment Category'
        category = self.get_object()
        ctx['linked_types'] = category.investment_types.all().prefetch_related('investments')
        ctx['total_linked_types'] = ctx['linked_types'].count()
        return ctx


class InvestmentCategoryDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    """Delete an investment category."""
    model = InvestmentCategory
    template_name = 'investments/category_confirm_delete.html'
    success_url = reverse_lazy('investments:category_list')
