from pathlib import Path
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy
from django.db.models import Sum
from decimal import Decimal
from .models import (
    Loan, Collateral, LoanGuarantor, LoanRollover,
    SystemSetting, LoanProduct, NonMemberApplicant, LoanApplication,
    LoanRestructure, RepaymentSchedule,
)
from .forms import (
    LoanForm, LoanAdjustForm, CollateralForm, LoanGuarantorForm,
    LoanProductForm,
    NonMemberApplicantForm, NonMemberQualifyForm,
    LoanApplicationForm, LoanApplicationReviewForm,
    LoanRestructureRequestForm, LoanRestructureRejectForm,
)
from .restructuring import (
    recalculate_schedule, apply_restructure, reject_restructure,
    check_max_restructures_limit,
)
from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin, MemberAccessMixin, AdminPasswordDeleteMixin
from utils.exports import export_csv, export_pdf
from django.contrib import messages
from django.db import transaction
from django.utils import timezone


class LoanListView(MemberAccessMixin, ListView):
    model = Loan
    template_name = 'loans/loan_list.html'
    context_object_name = 'loans'
    paginate_by = 20

    def get_queryset(self):
        from django.db.models import Exists, OuterRef, Q
        qs = Loan.objects.select_related('member', 'non_member').annotate(
            has_approved_restructure=Exists(
                LoanRestructure.objects.filter(loan=OuterRef('pk'), status='APPROVED')
            )
        )
        status = self.request.GET.get('status')
        q = self.request.GET.get('q', '').strip()
        borrower_type = self.request.GET.get('borrower_type', '').strip()
        
        if status == 'unpaid':
            qs = qs.filter(status__in=['active', 'late'])
        elif status == 'restructured':
            qs = qs.filter(Q(status='restructured') | Q(has_approved_restructure=True))
        elif status:
            qs = qs.filter(status=status)
            
        if borrower_type:
            qs = qs.filter(borrower_type=borrower_type)
        if q:
            qs = qs.filter(
                Q(member__name__icontains=q) | Q(non_member__full_name__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        from django.db.models import Q
        ctx = super().get_context_data(**kwargs)
        all_loans = Loan.objects.all()
        total_loans_val = all_loans.aggregate(t=Sum('loan_amount'))['t'] or Decimal('0')
        total_paid_val = all_loans.aggregate(t=Sum('amount_paid'))['t'] or Decimal('0')
        total_balance_val = sum(l.balance for l in all_loans)
        total_interest_val = sum(l.total_payable - l.loan_amount for l in all_loans)
        
        ctx['total_loans'] = total_loans_val
        ctx['total_interest'] = total_interest_val
        ctx['total_paid'] = total_paid_val
        ctx['total_balance'] = total_balance_val
        ctx['total_count'] = all_loans.count()
        ctx['active_count'] = all_loans.filter(status='active').count()
        ctx['cleared_count'] = all_loans.filter(status='cleared').count()
        ctx['late_count'] = all_loans.filter(status='late').count()
        ctx['unpaid_count'] = all_loans.filter(status__in=['active', 'late']).count()
        ctx['restructured_count'] = all_loans.filter(
            Q(status='restructured') | Q(restructures__status='APPROVED')
        ).distinct().count()
        ctx['non_member_count'] = all_loans.filter(borrower_type='non_member').count()
        
        total_portfolio_payable = total_paid_val + total_balance_val
        ctx['recovery_rate'] = round(float((total_paid_val / total_portfolio_payable) * 100), 1) if total_portfolio_payable > 0 else 0
        
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['current_borrower_type'] = self.request.GET.get('borrower_type', '')
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class LoanCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = Loan
    form_class = LoanForm
    template_name = 'loans/loan_form.html'
    success_url = reverse_lazy('loans:list')
    success_message = "Loan issued successfully."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from members.models import Member
        from utils.financials import get_available_fund_balance
        from .models import get_default_interest_rate
        ctx['all_members'] = Member.objects.all()
        ctx['available_fund_balance'] = get_available_fund_balance()
        ctx['default_rate_pct'] = float(get_default_interest_rate()) * 100
        ctx['loan_products'] = LoanProduct.objects.filter(is_active=True)
        ctx['qualified_non_members'] = NonMemberApplicant.objects.filter(
            qualification_status='qualified'
        ).order_by('full_name')
        return ctx

    def form_valid(self, form):
        from django.db import transaction
        from django.contrib import messages as msg
        from utils.financials import get_available_fund_balance

        loan_amount = form.cleaned_data.get('loan_amount')
        fund_source = form.cleaned_data.get('fund_source', 'group_funds')
        fund_source_bank = form.cleaned_data.get('fund_source_bank')

        # Only check group fund balance when source is group funds
        if fund_source == 'group_funds':
            available = get_available_fund_balance()
            if loan_amount and loan_amount > available:
                msg.error(
                    self.request,
                    f'Loan amount KES {loan_amount:,.2f} exceeds the available fund balance '
                    f'of KES {available:,.2f}. Please reduce the loan amount or wait for more funds.'
                )
                return self.form_invalid(form)
        elif fund_source == 'bank_account':
            if not fund_source_bank:
                msg.error(self.request, 'Please select a bank account as the fund source.')
                return self.form_invalid(form)
            bank_balance = fund_source_bank.current_balance
            if loan_amount and loan_amount > bank_balance:
                msg.error(
                    self.request,
                    f'Loan amount KES {loan_amount:,.2f} exceeds the '
                    f'{fund_source_bank.bank_name} balance of KES {bank_balance:,.2f}.'
                )
                return self.form_invalid(form)

        borrower_type = form.cleaned_data.get('borrower_type', 'member')
        member = form.cleaned_data.get('member')
        valid_guarantors = []

        # Validate guarantor coverage BEFORE saving to avoid broken atomic transactions
        if borrower_type == 'member' and member:
            guarantor_ids = self.request.POST.getlist('guarantor_ids[]')
            guarantor_amounts = self.request.POST.getlist('guarantor_amounts[]')

            member_contrib = member.total_contributions() or Decimal('0')
            shortfall = max(loan_amount - member_contrib, Decimal('0'))
            total_guaranteed = Decimal('0')
            errors = []

            for gid, amt_str in zip(guarantor_ids, guarantor_amounts):
                try:
                    from members.models import Member as M
                    g = M.objects.get(pk=gid)
                    amt = Decimal(amt_str or '0')
                    if amt <= 0:
                        continue
                    g_contributions = g.total_contributions() or Decimal('0')
                    if amt > g_contributions:
                        errors.append(
                            f"{g.name} can only guarantee up to KES {g_contributions:,.2f} "
                            f"(their total contributions). You entered KES {amt:,.2f}."
                        )
                        continue
                    if shortfall > 0 and amt > shortfall:
                        errors.append(
                            f"{g.name} cannot guarantee KES {amt:,.2f} because the total loan shortfall is KES {shortfall:,.2f}."
                        )
                        continue
                    if g != member:
                        valid_guarantors.append((g, amt))
                        total_guaranteed += amt
                except (M.DoesNotExist, ValueError, TypeError) as e:
                    errors.append(f"Could not process guarantor #{gid}: {e}")

            if shortfall > 0:
                if total_guaranteed < shortfall:
                    gap = shortfall - total_guaranteed
                    err = (
                        f"Guarantor coverage insufficient. "
                        f"Need KES {shortfall:,.2f}, got KES {total_guaranteed:,.2f}. "
                        f"Shortfall: KES {gap:,.2f}."
                    )
                    if errors:
                        err += " Also: " + " | ".join(errors)
                    msg.error(self.request, err)
                    return self.form_invalid(form)
                elif total_guaranteed > shortfall:
                    excess = total_guaranteed - shortfall
                    err = (
                        f"Guarantor coverage cannot exceed the requested loan shortfall. "
                        f"Required Target: KES {shortfall:,.2f}, Total Guaranteed: KES {total_guaranteed:,.2f}. "
                        f"Excess: KES {excess:,.2f}. Please reduce guarantor allocation."
                    )
                    if errors:
                        err += " Also: " + " | ".join(errors)
                    msg.error(self.request, err)
                    return self.form_invalid(form)
            elif shortfall == 0 and total_guaranteed > 0:
                msg.error(
                    self.request,
                    f"This borrower's contributions (KES {member_contrib:,.2f}) fully cover the loan amount (KES {loan_amount:,.2f}). "
                    f"No guarantor allocation is permitted."
                )
                return self.form_invalid(form)

            for e in errors:
                msg.warning(self.request, e)

        with transaction.atomic():
            response = super().form_valid(form)
            loan = self.object

            # Deduct from bank account balance when bank is the fund source
            if loan.fund_source == 'bank_account' and loan.fund_source_bank:
                from bank_accounts.models import BankBalance
                from django.utils import timezone
                bank_account = loan.fund_source_bank
                current_bal = bank_account.current_balance
                new_bal = current_bal - loan.loan_amount
                BankBalance.objects.create(
                    account=bank_account,
                    balance=new_bal,
                    topup_amount=loan.loan_amount,
                    transaction_type=BankBalance.TYPE_DEDUCTION,
                    recorded_on=timezone.localdate(),
                    notes=f'Loan #{loan.pk} issued to {loan.borrower_name}: '
                          f'KES {loan.loan_amount:,.2f} deducted.',
                    recorded_by=self.request.user,
                )

            # Create validated guarantor records
            for g, amt in valid_guarantors:
                LoanGuarantor.objects.get_or_create(
                    loan=loan, guarantor=g,
                    defaults={'amount_guaranteed': amt}
                )

        return response



class LoanUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Loan
    form_class = LoanAdjustForm
    template_name = 'loans/loan_form.html'
    success_url = reverse_lazy('loans:list')
    success_message = "Loan updated."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from .models import get_default_interest_rate
        ctx['default_rate_pct'] = float(get_default_interest_rate()) * 100
        return ctx

    def get_initial(self):
        initial = super().get_initial()
        # Pre-populate duration_months as string so ChoiceField matches correctly
        initial['duration_months'] = str(self.object.duration_months)
        return initial

    def form_valid(self, form):
        loan = form.save(commit=False)
        from decimal import Decimal
        import calendar
        from django.utils import timezone as tz
        from .models import get_default_interest_rate

        # Apply the manually-set penalty months from the adjust form
        loan.late_penalty_months = form.cleaned_data.get('late_penalty_months', 0)
        interest, total_base, monthly = loan._compute_interest()
        loan.interest_amount = interest
        loan.monthly_installment = monthly

        if loan.loan_type == 'emergency' or (loan.product and (loan.product.is_emergency or loan.product.interest_type == 'emergency')):
            loan.loan_type = 'emergency'
            loan.interest_rate = Decimal('0.0000')
            loan.late_penalty_per_month = Decimal('0.00')
            loan.accumulated_penalties = Decimal('0.00')
        elif loan.loan_type == 'flat':
            rate = Decimal(str(loan.interest_rate)) if loan.interest_rate is not None else get_default_interest_rate()
            loan.late_penalty_per_month = (Decimal(str(loan.loan_amount)) * rate).quantize(Decimal('0.01'))
            loan.accumulated_penalties = (loan.late_penalty_per_month * loan.late_penalty_months).quantize(Decimal('0.01'))
        elif loan.accumulated_penalties is None:
            loan.accumulated_penalties = Decimal('0.00')

        loan.total_payable = (total_base + loan.accumulated_penalties).quantize(Decimal('0.01'))

        # Always recalculate due_date from date_taken + duration_months
        if loan.date_taken:
            month = loan.date_taken.month - 1 + loan.duration_months
            year = loan.date_taken.year + month // 12
            month = month % 12 + 1
            day = min(loan.date_taken.day, calendar.monthrange(year, month)[1])
            loan.due_date = tz.localdate().replace(year=year, month=month, day=day)

        # Auto-derive status
        today = tz.localdate()
        if loan.amount_paid >= loan.total_payable:
            loan.status = 'cleared'
        elif loan.due_date and today > loan.due_date:
            loan.status = 'late'
        else:
            loan.status = 'active'

        loan.save()
        return super(SuccessMessageMixin, self).form_valid(form)

    def get_success_url(self):
        return reverse_lazy('loans:detail', kwargs={'pk': self.object.pk})


class LoanDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = Loan
    template_name = 'loans/loan_confirm_delete.html'
    success_url = reverse_lazy('loans:list')

    def form_valid(self, form):
        from django.contrib import messages
        loan = self.get_object()
        # If this loan was funded from a bank account, refund the remaining net balance to avoid ledger leaks
        if loan.fund_source == 'bank_account' and loan.fund_source_bank:
            from bank_accounts.models import BankBalance
            from django.utils import timezone
            net_deducted = loan.loan_amount - loan.amount_paid
            if net_deducted > Decimal('0.00'):
                new_bal = loan.fund_source_bank.current_balance + net_deducted
                BankBalance.objects.create(
                    account=loan.fund_source_bank,
                    balance=new_bal,
                    topup_amount=net_deducted,
                    transaction_type=BankBalance.TYPE_TOPUP,
                    recorded_on=timezone.localdate(),
                    notes=f'Loan #{loan.pk} deleted/cancelled: KES {net_deducted:,.2f} refunded.',
                    recorded_by=self.request.user,
                )
        messages.success(self.request, f"Loan #{loan.pk} deleted successfully.")
        return super().form_valid(form)


class LoanDetailView(MemberAccessMixin, DetailView):
    model = Loan
    template_name = 'loans/loan_detail.html'
    context_object_name = 'loan'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['payments'] = self.object.payment_set.select_related('member').all()
        return ctx


class LoanCalculatorView(MemberAccessMixin, View):
    """AJAX endpoint — returns interest preview for flat or reducing balance loans."""
    def get(self, request):
        try:
            from decimal import Decimal
            from .models import get_default_interest_rate
            amount = Decimal(request.GET.get('amount', '0'))
            months = int(request.GET.get('months', '1'))
            rate_str = request.GET.get('rate', '')
            loan_type = request.GET.get('loan_type', 'flat')

            if rate_str:
                rate = (Decimal(rate_str) / Decimal('100')).quantize(Decimal('0.0001'))
            else:
                rate = get_default_interest_rate()

            if amount <= 0 or months <= 0:
                raise ValueError

            if loan_type == 'emergency':
                return JsonResponse({
                    'loan_type': 'emergency',
                    'total_interest': '0.00',
                    'total_payable': str(amount.quantize(Decimal('0.01'))),
                    'rate_percent': '0.00',
                })

            if loan_type == 'reducing_principal':
                # Equal principal repayment
                pp = amount / Decimal(months)
                balance = amount
                total_interest = Decimal('0.00')
                first_inst = Decimal('0.00')
                schedule = []
                for i in range(1, months + 1):
                    month_interest = (balance * rate).quantize(Decimal('0.01'))
                    installment = (pp + month_interest).quantize(Decimal('0.01'))
                    if i == 1:
                        first_inst = installment
                    total_interest += month_interest
                    balance = max(balance - pp, Decimal('0'))
                    schedule.append({
                        'month': i,
                        'installment': str(installment),
                        'interest': str(month_interest),
                        'principal': str(pp.quantize(Decimal('0.01'))),
                        'balance': str(balance.quantize(Decimal('0.01'))),
                    })
                total = (amount + total_interest).quantize(Decimal('0.01'))
                return JsonResponse({
                    'loan_type': 'reducing_principal',
                    'first_installment': str(first_inst),
                    'monthly_installment': str(first_inst),
                    'total_interest': str(total_interest),
                    'total_payable': str(total),
                    'rate_percent': str(float(rate) * 100),
                    'schedule': schedule,
                })
            elif loan_type == 'reducing':
                if rate == 0:
                    monthly = (amount / Decimal(months)).quantize(Decimal('0.01'))
                    total = (monthly * months).quantize(Decimal('0.01'))
                    interest = Decimal('0.00')
                else:
                    r = float(rate)
                    M = float(amount) * r / (1 - (1 + r) ** (-months))
                    monthly = Decimal(str(round(M, 2)))
                    total = (monthly * months).quantize(Decimal('0.01'))
                    interest = (total - amount).quantize(Decimal('0.01'))

                # Build a simple schedule for the first few months
                schedule = []
                balance = amount
                r = float(rate)
                for i in range(1, months + 1):
                    month_interest = (balance * rate).quantize(Decimal('0.01'))
                    principal_paid = (monthly - month_interest).quantize(Decimal('0.01'))
                    balance = max(balance - principal_paid, Decimal('0'))
                    schedule.append({
                        'month': i,
                        'installment': str(monthly),
                        'interest': str(month_interest),
                        'principal': str(principal_paid),
                        'balance': str(balance),
                    })

                return JsonResponse({
                    'loan_type': 'reducing',
                    'monthly_installment': str(monthly),
                    'total_interest': str(interest),
                    'total_payable': str(total),
                    'rate_percent': str(float(rate) * 100),
                    'schedule': schedule,
                })
            else:
                interest = (amount * rate).quantize(Decimal('0.01'))
                total = amount + interest
                return JsonResponse({
                    'loan_type': 'flat',
                    'total_interest': str(interest),
                    'total_payable': str(total),
                    'rate_percent': str(float(rate) * 100),
                })
        except Exception:
            return JsonResponse({'error': 'Invalid input'}, status=400)


class MemberContributionCheckView(MemberAccessMixin, View):
    """AJAX — returns member's total contributions and eligible guarantors."""
    def get(self, request):
        from members.models import Member
        member_id = request.GET.get('member_id')
        loan_amount_str = request.GET.get('amount', '0')
        try:
            member = Member.objects.get(pk=member_id)
            total_contributions = member.total_contributions() or Decimal('0')
            loan_amount = Decimal(loan_amount_str or '0')
            shortfall = max(loan_amount - total_contributions, Decimal('0'))
            needs_guarantor = shortfall > 0

            # Eligible guarantors: no active/late loan, excluding borrower
            active_loan_ids = Loan.objects.filter(
                status__in=['active', 'late']
            ).values_list('member_id', flat=True)
            eligible = Member.objects.exclude(pk=member.pk).exclude(pk__in=active_loan_ids)
            guarantors = [
                {
                    'id': m.pk,
                    'name': m.name,
                    'phone': m.phone,
                    'contributions': float(m.total_contributions() or 0),
                    'max_guarantee': float(m.total_contributions() or 0),
                }
                for m in eligible
            ]
            return JsonResponse({
                'total_contributions': float(total_contributions),
                'needs_guarantor': needs_guarantor,
                'shortfall': float(shortfall),
                'guarantors': guarantors,
            })
        except Member.DoesNotExist:
            return JsonResponse({'error': 'Member not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)


class CollateralCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = Collateral
    form_class = CollateralForm
    template_name = 'loans/collateral_form.html'
    success_message = "Collateral added."

    def form_valid(self, form):
        form.instance.loan_id = self.kwargs['loan_pk']
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('loans:detail', kwargs={'pk': self.kwargs['loan_pk']})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['loan'] = Loan.objects.get(pk=self.kwargs['loan_pk'])
        return ctx


class CollateralDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = Collateral
    template_name = 'loans/collateral_confirm_delete.html'

    def get_success_url(self):
        return reverse_lazy('loans:detail', kwargs={'pk': self.object.loan_id})


class GuarantorAddView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = LoanGuarantor
    form_class = LoanGuarantorForm
    template_name = 'loans/guarantor_form.html'
    success_message = "Guarantor added."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['loan'] = Loan.objects.get(pk=self.kwargs['loan_pk'])
        return kwargs

    def form_valid(self, form):
        form.instance.loan_id = self.kwargs['loan_pk']
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('loans:detail', kwargs={'pk': self.kwargs['loan_pk']})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['loan'] = Loan.objects.get(pk=self.kwargs['loan_pk'])
        return ctx


class GuarantorDeleteView(AdminPasswordDeleteMixin, TreasurerRequiredMixin, DeleteView):
    model = LoanGuarantor
    template_name = 'loans/guarantor_confirm_delete.html'

    def get_success_url(self):
        return reverse_lazy('loans:detail', kwargs={'pk': self.object.loan_id})


class LoanRolloverView(TreasurerRequiredMixin, View):
    """Confirm + execute a loan rollover."""

    def get(self, request, pk):
        loan = Loan.objects.get(pk=pk)
        if loan.status == 'cleared' or loan.balance <= 0:
            from django.contrib import messages
            messages.error(request, "This loan is already cleared and cannot be rolled over.")
            return redirect('loans:detail', pk=pk)
        from decimal import Decimal
        from utils.financials import get_available_fund_balance
        outstanding = loan.balance
        rate = Decimal(str(loan.interest_rate))
        if loan.loan_type == 'reducing' and rate > 0:
            r = float(rate)
            M = float(outstanding) * r / (1 - (1 + r) ** (-loan.duration_months))
            monthly = Decimal(str(round(M, 2)))
            new_total = (monthly * loan.duration_months).quantize(Decimal('0.01'))
            new_interest = (new_total - outstanding).quantize(Decimal('0.01'))
        elif loan.loan_type == 'emergency':
            new_interest = Decimal('0.00')
            new_total = outstanding
        else:
            new_interest = (outstanding * rate).quantize(Decimal('0.01'))
            new_total = (outstanding + new_interest).quantize(Decimal('0.01'))
        available = get_available_fund_balance()
        return render(request, 'loans/loan_rollover_confirm.html', {
            'loan': loan,
            'outstanding': outstanding,
            'new_interest': new_interest,
            'new_total': new_total,
            'rate_percent': float(rate) * 100,
            'duration_choices': range(1, 25),
            'available_fund_balance': available,
        })

    def post(self, request, pk):
        loan = Loan.objects.get(pk=pk)
        if loan.status == 'cleared' or loan.balance <= 0:
            from django.contrib import messages
            messages.error(request, "This loan is already cleared and cannot be rolled over.")
            return redirect('loans:detail', pk=pk)
        duration = int(request.POST.get('duration_months', loan.duration_months))
        try:
            loan.do_rollover(duration_months=duration)
            from django.contrib import messages
            messages.success(request, f"Loan #{loan.pk} rolled over. New balance: KES {loan.total_payable:,.2f}")
        except Exception as e:
            from django.contrib import messages
            messages.error(request, f"Rollover failed: {e}")
        return redirect('loans:detail', pk=pk)


class GuarantorsReportView(MemberAccessMixin, TemplateView):
    template_name = 'loans/guarantors_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from django.core.paginator import Paginator
        qs = (
            LoanGuarantor.objects
            .select_related('guarantor', 'loan__member')
            .order_by('guarantor__name')
        )
        paginator = Paginator(qs, 20)
        page = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page)
        ctx['guarantors'] = page_obj
        ctx['page_obj'] = page_obj
        ctx['total_count'] = qs.count()
        return ctx


class LoanExportView(MemberAccessMixin, View):
    def get(self, request):
        format_type = request.GET.get('format', 'csv')
        qs = Loan.objects.select_related('member', 'non_member')
        status = request.GET.get('status', '').strip()
        q = request.GET.get('q', '').strip()
        if status == 'unpaid':
            qs = qs.filter(status__in=['active', 'late'])
        elif status:
            qs = qs.filter(status=status)
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(member__name__icontains=q) | Q(non_member__full_name__icontains=q)
            )

        fields = [
            (lambda obj: obj.borrower_name, 'Borrower'),
            (lambda obj: obj.get_borrower_type_display(), 'Type'),
            ('loan_amount', 'Principal (KES)'),
            ('interest_amount', 'Interest (KES)'),
            ('total_payable', 'Total Payable (KES)'),
            ('amount_paid', 'Paid (KES)'),
            (lambda obj: f"{obj.balance:,.2f}", 'Balance (KES)'),
            ('status', 'Status'),
            ('date_taken', 'Date Taken'),
            ('due_date', 'Due Date'),
        ]
        if format_type == 'pdf':
            return export_pdf(qs, 'loans', 'Loans Report', fields, orientation='landscape')
        return export_csv(qs, 'loans', fields)




# ── System Settings ───────────────────────────────────────────────

class LoanSettingsView(AdminRequiredMixin, View):
    template_name = 'loans/settings.html'

    SETTINGS_SCHEMA = [
        {
            'key': 'default_interest_rate',
            'label': 'Default Interest Rate (%)',
            'help_text': (
                'Flat one-off rate automatically pre-filled when issuing a new loan. '
                'Enter as a percentage, e.g. 10 for 10%. '
                'Individual loans can still override this.'
            ),
            'default': '10',
            'input_type': 'number',
            'step': '0.01',
            'min': '0',
            'max': '100',
        },
    ]

    def _get_current(self):
        """Return a list of settings dicts with current values merged in."""
        result = []
        for s in self.SETTINGS_SCHEMA:
            value = SystemSetting.get(s['key'], s['default'])
            result.append({**s, 'value': value})
        return result

    def get(self, request):
        return render(request, self.template_name, {
            'settings_list': self._get_current(),
        })

    def post(self, request):
        from django.contrib import messages as msg
        errors = []

        for s in self.SETTINGS_SCHEMA:
            raw = request.POST.get(s['key'], '').strip()
            if not raw:
                errors.append(f"{s['label']}: value is required.")
                continue

            # Validate numeric settings
            try:
                val = float(raw)
                if 'min' in s and val < float(s['min']):
                    errors.append(f"{s['label']}: must be ≥ {s['min']}.")
                    continue
                if 'max' in s and val > float(s['max']):
                    errors.append(f"{s['label']}: must be ≤ {s['max']}.")
                    continue
            except ValueError:
                errors.append(f"{s['label']}: must be a valid number.")
                continue

            # Store interest rate as decimal (10 → 0.1)
            if s['key'] == 'default_interest_rate':
                stored = str(round(val / 100, 6))
            else:
                stored = raw

            SystemSetting.set(s['key'], stored, label=s['label'], help_text=s['help_text'])

        if errors:
            for e in errors:
                msg.error(request, e)
        else:
            msg.success(request, 'Settings saved successfully.')

        return render(request, self.template_name, {
            'settings_list': self._get_current(),
        })


# ── Group / Chama Settings ────────────────────────────────────────

class GroupSettingsView(AdminRequiredMixin, View):
    template_name = 'loans/group_settings.html'

    def get(self, request):
        from loans.models import THEME_PRESETS
        info = SystemSetting.get_group_info()
        active_tab = request.GET.get('tab', 'profile')
        return render(request, self.template_name, {
            'info': info,
            'theme_presets': THEME_PRESETS,
            'active_tab': active_tab,
        })

    def post(self, request):
        import os
        from decimal import Decimal, InvalidOperation
        from django.conf import settings as django_settings
        from django.contrib import messages as msg
        from django.urls import reverse
        from loans.models import THEME_PRESETS

        active_tab = request.POST.get('active_tab', 'profile')
        errors = []

        # 1. Profile fields
        if active_tab == 'profile' or 'group_name' in request.POST:
            group_name = request.POST.get('group_name', '').strip()
            if not group_name:
                errors.append("Group Name is required.")
            else:
                SystemSetting.set('group_name', group_name, label='Group Name')

            SystemSetting.set('group_tagline', request.POST.get('group_tagline', '').strip(), label='Tagline')
            SystemSetting.set('group_currency', request.POST.get('group_currency', 'KES').strip().upper() or 'KES', label='Currency')
            SystemSetting.set('group_location', request.POST.get('group_location', '').strip(), label='Location')
            SystemSetting.set('group_postal_address', request.POST.get('group_postal_address', '').strip(), label='Postal Address')
            SystemSetting.set('group_phone', request.POST.get('group_phone', '').strip(), label='Phone Number')
            SystemSetting.set('group_email', request.POST.get('group_email', '').strip(), label='Email Address')
            SystemSetting.set('group_registration', request.POST.get('group_registration', '').strip(), label='Registration Number')
            SystemSetting.set('group_founded', request.POST.get('group_founded', '').strip(), label='Year Founded')

        # 2. Logo Upload & Removal
        if active_tab == 'logo' or 'logo_file' in request.FILES or request.POST.get('remove_logo') == '1':
            if request.POST.get('remove_logo') == '1':
                try:
                    old_logo = SystemSetting.get('group_logo', '')
                    if old_logo:
                        old_rel = old_logo.lstrip('/')
                        if old_rel.startswith('media/'):
                            old_rel = old_rel[6:]
                        old_path = Path(django_settings.MEDIA_ROOT) / old_rel
                        if old_path.exists():
                            try:
                                old_path.unlink()
                            except OSError:
                                pass
                    SystemSetting.set('group_logo', '', label='Group Logo')
                    msg.info(request, "Group logo removed.")
                except Exception as exc:
                    errors.append(f"Failed to remove logo: {exc}")
            elif 'logo_file' in request.FILES:
                try:
                    logo_file = request.FILES['logo_file']
                    valid_extensions = ['.png', '.jpg', '.jpeg', '.webp', '.svg', '.gif']
                    ext = os.path.splitext(logo_file.name)[1].lower()
                    if ext not in valid_extensions:
                        errors.append(f"Invalid image format ({ext}). Supported formats: PNG, JPG, JPEG, WEBP, SVG, GIF.")
                    elif logo_file.size > 3 * 1024 * 1024:
                        errors.append("Logo image size must not exceed 3MB.")
                    else:
                        import time
                        branding_dir = Path(django_settings.MEDIA_ROOT) / 'branding'
                        branding_dir.mkdir(parents=True, exist_ok=True)
                        
                        # Use a unique timestamped filename to prevent Windows file-lock errors
                        # when overwriting an image file currently open by Waitress or WebView
                        filename = f"group_logo_{int(time.time())}{ext}"
                        filepath = branding_dir / filename
                        with open(filepath, 'wb+') as destination:
                            for chunk in logo_file.chunks():
                                destination.write(chunk)

                        # Clean up previous logo file if it exists and is not the new file
                        old_logo = SystemSetting.get('group_logo', '')
                        if old_logo:
                            old_rel = old_logo.lstrip('/')
                            if old_rel.startswith('media/'):
                                old_rel = old_rel[6:]
                            old_path = Path(django_settings.MEDIA_ROOT) / old_rel
                            if old_path.exists() and old_path.resolve() != filepath.resolve():
                                try:
                                    old_path.unlink()
                                except Exception:
                                    pass  # Safe to ignore if active handle is still held

                        logo_url = f"{django_settings.MEDIA_URL}branding/{filename}"
                        SystemSetting.set('group_logo', logo_url, label='Group Logo')
                        msg.success(request, "Group logo updated successfully.")
                except Exception as exc:
                    errors.append(f"Could not upload logo: {exc}")

        # 3. Theme & Appearance
        if active_tab == 'theme' or 'theme_preset' in request.POST:
            theme_preset = request.POST.get('theme_preset', '').strip()
            use_custom = request.POST.get('use_custom_theme') == '1'

            if theme_preset in THEME_PRESETS and not use_custom:
                p = THEME_PRESETS[theme_preset]
                SystemSetting.set('theme_preset', theme_preset, label='Color Theme Preset')
                SystemSetting.set('theme_sidebar_bg', '#1e2a3a', label='Sidebar Background Color')
                SystemSetting.set('theme_primary_color', p['primary_color'], label='Primary Accent Color')
                SystemSetting.set('theme_sidebar_hover', '#2c3e52', label='Sidebar Hover Color')
                SystemSetting.set('theme_sidebar_text', '#94a3b8', label='Sidebar Text Color')
                SystemSetting.set('theme_sidebar_section', '#475569', label='Sidebar Section Header Color')
            elif use_custom:
                custom_primary = request.POST.get('custom_primary_color', '').strip()
                SystemSetting.set('theme_sidebar_bg', '#1e2a3a', label='Sidebar Background Color')
                if custom_primary:
                    SystemSetting.set('theme_primary_color', custom_primary, label='Custom Primary Accent')
                SystemSetting.set('theme_preset', 'custom', label='Color Theme Preset')

        # 4. Financial Rules
        if active_tab == 'financial' or 'default_interest_rate' in request.POST:
            ir_str = request.POST.get('default_interest_rate', '').strip()
            pr_str = request.POST.get('default_late_penalty_rate', '').strip()
            gp_str = request.POST.get('grace_period_days', '0').strip()
            max_l_str = request.POST.get('max_active_loans_per_member', '0').strip()
            mult_str = request.POST.get('savings_loan_multiplier', '0').strip()

            if ir_str:
                try:
                    ir = Decimal(ir_str)
                    if ir < 0: raise ValueError
                    SystemSetting.set('default_interest_rate', str(ir), label='Default Interest Rate (%)')
                except (InvalidOperation, ValueError):
                    errors.append("Invalid Default Interest Rate.")

            if pr_str:
                try:
                    pr = Decimal(pr_str)
                    if pr < 0: raise ValueError
                    SystemSetting.set('default_late_penalty_rate', str(pr), label='Default Late Penalty Rate (%)')
                except (InvalidOperation, ValueError):
                    errors.append("Invalid Late Penalty Rate.")

            if gp_str:
                try:
                    gp = int(gp_str)
                    if gp < 0: raise ValueError
                    SystemSetting.set('grace_period_days', str(gp), label='Grace Period (Days)')
                except ValueError:
                    errors.append("Grace Period must be a non-negative integer.")

            if max_l_str:
                try:
                    ml = int(max_l_str)
                    if ml < 0: raise ValueError
                    SystemSetting.set('max_active_loans_per_member', str(ml), label='Max Active Loans')
                except ValueError:
                    errors.append("Max Active Loans must be a non-negative integer.")

            if mult_str:
                try:
                    mult = Decimal(mult_str)
                    if mult < 0: raise ValueError
                    SystemSetting.set('savings_loan_multiplier', str(mult), label='Savings Multiplier')
                except (InvalidOperation, ValueError):
                    errors.append("Invalid Savings Multiplier.")

        # 5. Document & PDF Branding
        if active_tab == 'documents' or 'pdf_header_title' in request.POST:
            SystemSetting.set('pdf_header_title', request.POST.get('pdf_header_title', '').strip(), label='PDF Header Title')
            SystemSetting.set('pdf_show_logo', '1' if request.POST.get('pdf_show_logo') == '1' else '0', label='Show Logo on PDF')
            SystemSetting.set('pdf_show_contact', '1' if request.POST.get('pdf_show_contact') == '1' else '0', label='Show Contact on PDF')

        if errors:
            for e in errors:
                msg.error(request, e)
        else:
            if active_tab != 'logo':
                msg.success(request, "Settings saved successfully. Changes are live immediately.")

        return redirect(f"{reverse('loans:group_settings')}?tab={active_tab}")


# ── Loan Products ─────────────────────────────────────────────────

class LoanProductListView(AdminRequiredMixin, ListView):
    model = LoanProduct
    template_name = 'loans/product_list.html'
    context_object_name = 'products'
    queryset = LoanProduct.objects.all()


class LoanProductCreateView(AdminRequiredMixin, SuccessMessageMixin, CreateView):
    model = LoanProduct
    form_class = LoanProductForm
    template_name = 'loans/product_form.html'
    success_url = reverse_lazy('loans:product_list')
    success_message = "Loan product created."


class LoanProductUpdateView(AdminRequiredMixin, SuccessMessageMixin, UpdateView):
    model = LoanProduct
    form_class = LoanProductForm
    template_name = 'loans/product_form.html'
    success_url = reverse_lazy('loans:product_list')
    success_message = "Loan product updated."


class LoanProductDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = LoanProduct
    template_name = 'loans/product_confirm_delete.html'
    success_url = reverse_lazy('loans:product_list')

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 302:
            from django.contrib import messages
            messages.success(request, "Loan product deleted.")
        return response


class LoanProductDetailAPIView(MemberAccessMixin, View):
    """AJAX — returns a product's fields as JSON for auto-filling the loan form."""
    def get(self, request, pk):
        try:
            p = LoanProduct.objects.get(pk=pk)
            return JsonResponse({
                'interest_type':   p.interest_type,
                'loan_type':       p.loan_type_for_calc,
                'interest_rate':   float(p.interest_rate),
                'duration_months': p.duration_months,
                'min_amount':      float(p.min_amount),
                'max_amount':      float(p.max_amount),
                'description':     p.description,
                'frequency':       p.interest_frequency,
                'is_emergency':    p.is_emergency or (p.interest_type == 'emergency'),
            })
        except LoanProduct.DoesNotExist:
            return JsonResponse({'error': 'Not found'}, status=404)


# ── Non-Member Applicants ─────────────────────────────────────────

class NonMemberApplicantListView(TreasurerRequiredMixin, ListView):
    model = NonMemberApplicant
    template_name = 'loans/non_member_list.html'
    context_object_name = 'applicants'
    paginate_by = 20

    def get_queryset(self):
        qs = NonMemberApplicant.objects.select_related('qualified_by')
        status = self.request.GET.get('status', '').strip()
        q = self.request.GET.get('q', '').strip()
        if status:
            qs = qs.filter(qualification_status=status)
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(full_name__icontains=q) | Q(phone__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['pending_count']       = NonMemberApplicant.objects.filter(qualification_status='pending').count()
        ctx['qualified_count']     = NonMemberApplicant.objects.filter(qualification_status='qualified').count()
        ctx['disqualified_count']  = NonMemberApplicant.objects.filter(qualification_status='disqualified').count()
        ctx['current_status']      = self.request.GET.get('status', '')
        ctx['q']                   = self.request.GET.get('q', '')
        return ctx


class NonMemberApplicantCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = NonMemberApplicant
    form_class = NonMemberApplicantForm
    template_name = 'loans/non_member_form.html'
    success_message = "Applicant registered. An admin can now assess their qualification."

    def get_success_url(self):
        return reverse_lazy('loans:non_member_detail', kwargs={'pk': self.object.pk})


class NonMemberApplicantDetailView(TreasurerRequiredMixin, View):
    template_name = 'loans/non_member_detail.html'

    def get(self, request, pk):
        applicant = get_object_or_404(NonMemberApplicant, pk=pk)
        qualify_form = NonMemberQualifyForm(instance=applicant)
        loans = applicant.loans.all()
        return render(request, self.template_name, {
            'applicant': applicant,
            'qualify_form': qualify_form,
            'loans': loans,
        })


class NonMemberApplicantUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = NonMemberApplicant
    form_class = NonMemberApplicantForm
    template_name = 'loans/non_member_form.html'
    success_message = "Applicant details updated."

    def get_success_url(self):
        return reverse_lazy('loans:non_member_detail', kwargs={'pk': self.object.pk})


class NonMemberApplicantDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = NonMemberApplicant
    template_name = 'loans/non_member_confirm_delete.html'
    success_url = reverse_lazy('loans:non_members')


class NonMemberQualifyView(TreasurerRequiredMixin, View):
    """Admin/treasurer sets qualification status on a non-member applicant."""

    def post(self, request, pk):
        from django.contrib import messages
        from django.utils import timezone
        applicant = get_object_or_404(NonMemberApplicant, pk=pk)
        form = NonMemberQualifyForm(request.POST, instance=applicant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.qualified_by = request.user
            obj.qualified_at = timezone.now()
            obj.save()
            label = obj.get_qualification_status_display()
            messages.success(request, f"{applicant.full_name} marked as {label}.")
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, e)
        return redirect('loans:non_member_detail', pk=pk)


# ── Loan Applications ─────────────────────────────────────────────

class LoanApplicationListView(MemberAccessMixin, ListView):
    model = LoanApplication
    template_name = 'loans/application_list.html'
    context_object_name = 'applications'
    paginate_by = 20

    def get_queryset(self):
        qs = LoanApplication.objects.select_related('member', 'applied_by', 'reviewed_by', 'loan')
        status = self.request.GET.get('status', '').strip()
        q = self.request.GET.get('q', '').strip()
        if status:
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(member__name__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        all_apps = LoanApplication.objects.all()
        ctx['pending_count']  = all_apps.filter(status='pending').count()
        ctx['approved_count'] = all_apps.filter(status='approved').count()
        ctx['rejected_count'] = all_apps.filter(status='rejected').count()
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['q']              = self.request.GET.get('q', '')
        return ctx


class LoanApplicationCreateView(LoginRequiredMixin, SuccessMessageMixin, CreateView):
    model = LoanApplication
    form_class = LoanApplicationForm
    template_name = 'loans/application_form.html'
    success_url = reverse_lazy('loans:applications')
    success_message = "Loan application submitted successfully."

    def form_valid(self, form):
        form.instance.applied_by = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from utils.financials import get_available_fund_balance
        from .models import get_default_interest_rate
        ctx['available_fund_balance'] = get_available_fund_balance()
        ctx['default_rate_pct'] = float(get_default_interest_rate()) * 100
        return ctx


class LoanApplicationDetailView(MemberAccessMixin, View):
    template_name = 'loans/application_detail.html'

    def get(self, request, pk):
        from django.utils import timezone
        app = get_object_or_404(
            LoanApplication.objects.select_related('member', 'applied_by', 'reviewed_by', 'loan'),
            pk=pk
        )
        from utils.financials import get_available_fund_balance
        form = LoanApplicationReviewForm(initial={'date_taken': timezone.localdate()})
        return render(request, self.template_name, {
            'app': app,
            'form': form,
            'available_fund_balance': get_available_fund_balance(),
        })

    def post(self, request, pk):
        from django.contrib import messages
        from django.db import transaction
        from django.utils import timezone
        from utils.financials import get_available_fund_balance

        app = get_object_or_404(LoanApplication, pk=pk)
        if app.status != 'pending':
            messages.error(request, "This application has already been reviewed.")
            return redirect('loans:application_detail', pk=pk)

        # Only treasurer, admin or superuser can review
        if not (request.user.is_superuser or getattr(request.user, 'role', '') in ('admin', 'treasurer')):
            messages.error(request, "You do not have permission to review loan applications.")
            return redirect('loans:application_detail', pk=pk)

        form = LoanApplicationReviewForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'app': app,
                'form': form,
                'available_fund_balance': get_available_fund_balance(),
            })

        action = form.cleaned_data['action']
        review_notes = form.cleaned_data.get('review_notes', '')

        if action == 'reject':
            app.status = 'rejected'
            app.review_notes = review_notes
            app.reviewed_by = request.user
            app.reviewed_at = timezone.now()
            app.save()
            messages.success(request, f"Application #{app.pk} has been rejected.")
            return redirect('loans:application_detail', pk=pk)

        # Action is approve
        date_taken = form.cleaned_data['date_taken']
        fund_source = form.cleaned_data.get('fund_source', 'group_funds')
        fund_source_bank = form.cleaned_data.get('fund_source_bank')
        fund_source_label = form.cleaned_data.get('fund_source_label', '')

        # Check fund balance if group funds
        if fund_source == 'group_funds':
            available = get_available_fund_balance()
            if app.loan_amount > available:
                messages.error(
                    request,
                    f"Cannot approve loan: requested KES {app.loan_amount:,.2f} exceeds "
                    f"available fund balance of KES {available:,.2f}."
                )
                return redirect('loans:application_detail', pk=pk)
        elif fund_source == 'bank_account':
            if not fund_source_bank:
                messages.error(request, "Please select a bank account.")
                return redirect('loans:application_detail', pk=pk)
            if app.loan_amount > fund_source_bank.current_balance:
                messages.error(
                    request,
                    f"Cannot approve loan: requested KES {app.loan_amount:,.2f} exceeds "
                    f"{fund_source_bank.bank_name} balance of KES {fund_source_bank.current_balance:,.2f}."
                )
                return redirect('loans:application_detail', pk=pk)

        with transaction.atomic():
            loan = Loan.objects.create(
                member=app.member,
                borrower_type='member',
                loan_amount=app.loan_amount,
                duration_months=app.duration_months,
                date_taken=date_taken,
                fund_source=fund_source,
                fund_source_bank=fund_source_bank,
                fund_source_label=fund_source_label,
                notes=f"Created from Loan Application #{app.pk}. {app.reason}",
            )

            # Bank deduction if bank-funded
            if fund_source == 'bank_account' and fund_source_bank:
                from bank_accounts.models import BankBalance
                new_bal = fund_source_bank.current_balance - loan.loan_amount
                BankBalance.objects.create(
                    account=fund_source_bank,
                    balance=new_bal,
                    topup_amount=loan.loan_amount,
                    transaction_type=BankBalance.TYPE_DEDUCTION,
                    recorded_on=timezone.localdate(),
                    notes=f'Loan #{loan.pk} issued to {loan.borrower_name}: '
                          f'KES {loan.loan_amount:,.2f} deducted.',
                    recorded_by=request.user,
                )

            app.status = 'approved'
            app.reviewed_by = request.user
            app.reviewed_at = timezone.now()
            app.review_notes = review_notes
            app.loan = loan
            app.save()

        messages.success(request, f"Application approved! Loan #{loan.pk} has been issued.")
        return redirect('loans:detail', pk=loan.pk)


class LoanApplicationDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = LoanApplication
    template_name = 'loans/application_confirm_delete.html'
    success_url = reverse_lazy('loans:applications')

    def post(self, request, *args, **kwargs):
        messages.success(request, "Loan application deleted.")
        return super().post(request, *args, **kwargs)


# ── Loan Restructuring Views ───────────────────────────────────────

class LoanRestructureListView(MemberAccessMixin, ListView):
    """List all loan restructure requests and history."""
    model = LoanRestructure
    template_name = 'loans/restructure_list.html'
    context_object_name = 'restructures'
    paginate_by = 20

    def get_queryset(self):
        qs = LoanRestructure.objects.select_related(
            'loan', 'loan__member', 'loan__non_member', 'requested_by', 'approved_by'
        )
        status = self.request.GET.get('status')
        rtype = self.request.GET.get('type')
        if status:
            qs = qs.filter(status=status)
        if rtype:
            qs = qs.filter(restructure_type=rtype)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        all_qs = LoanRestructure.objects.all()
        ctx['total_requests'] = all_qs.count()
        ctx['pending_requests'] = all_qs.filter(status='PENDING').count()
        ctx['approved_requests'] = all_qs.filter(status='APPROVED').count()
        ctx['rejected_requests'] = all_qs.filter(status='REJECTED').count()
        ctx['active_tab'] = self.request.GET.get('status', 'all')
        return ctx


class LoanRestructureDetailView(MemberAccessMixin, DetailView):
    """View details of a restructure request including old vs new schedule snapshots."""
    model = LoanRestructure
    template_name = 'loans/restructure_detail.html'
    context_object_name = 'restructure'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['reject_form'] = LoanRestructureRejectForm()
        ctx['loan'] = self.object.loan
        return ctx


class LoanRestructureRequestView(TreasurerRequiredMixin, View):
    """Create a new Loan Restructure proposal."""
    template_name = 'loans/restructure_form.html'

    def get_loan(self, loan_pk):
        return get_object_or_404(
            Loan.objects.select_related('member', 'non_member'),
            pk=loan_pk
        )

    def get(self, request, loan_pk):
        loan = self.get_loan(loan_pk)
        if loan.status in ('cleared', 'written_off'):
            messages.error(request, f"Loan #{loan.pk} is {loan.get_status_display().lower()} and cannot be restructured.")
            return redirect('loans:detail', pk=loan.pk)

        try:
            check_max_restructures_limit(loan)
        except Exception as e:
            messages.error(request, str(e))
            return redirect('loans:detail', pk=loan.pk)

        form = LoanRestructureRequestForm(loan=loan, initial={
            'new_term_months': loan.duration_months,
            'new_rate': (loan.interest_rate * Decimal('100')).quantize(Decimal('0.01')) if loan.interest_rate else Decimal('10.00'),
        })

        return render(request, self.template_name, {
            'form': form,
            'loan': loan,
        })

    def post(self, request, loan_pk):
        loan = self.get_loan(loan_pk)
        form = LoanRestructureRequestForm(request.POST, loan=loan)

        if not form.is_valid():
            return render(request, self.template_name, {
                'form': form,
                'loan': loan,
            })

        cleaned = form.cleaned_data
        rtype = cleaned['restructure_type']
        
        # Build parameters dictionary
        params = {}
        if cleaned.get('new_term_months'):
            params['new_term_months'] = cleaned['new_term_months']
        if cleaned.get('new_rate') is not None:
            # Convert percentage input (e.g. 5.00) to decimal fraction (0.05)
            params['new_rate'] = str((cleaned['new_rate'] / Decimal('100')).quantize(Decimal('0.0001')))
        if cleaned.get('moratorium_months'):
            params['moratorium_months'] = cleaned['moratorium_months']
            params['accrue_interest'] = cleaned.get('accrue_interest', False)
            params['remaining_months'] = cleaned.get('remaining_months', loan.duration_months)
        if cleaned.get('consolidated_loans'):
            params['consolidated_loans'] = list(cleaned['consolidated_loans'])

        # Precompute proposed schedule snapshot
        try:
            new_schedule_preview = recalculate_schedule(
                loan=loan,
                restructure_type=rtype,
                params=params,
                as_of_date=timezone.localdate()
            )
        except Exception as e:
            form.add_error(None, f"Calculation error: {e}")
            return render(request, self.template_name, {
                'form': form,
                'loan': loan,
            })

        # Save restructure proposal
        with transaction.atomic():
            restructure = form.save(commit=False)
            restructure.loan = loan
            restructure.requested_by = request.user
            restructure.status = 'PENDING'
            restructure.parameters = {
                k: (str(v) if isinstance(v, Decimal) else ([x.pk for x in v] if isinstance(v, list) and v and hasattr(v[0], 'pk') else v))
                for k, v in params.items()
            }
            # Snapshot new schedule preview
            restructure.new_schedule_snapshot = [
                {
                    'installment_number': item['installment_number'],
                    'due_date': str(item['due_date']),
                    'principal_amount': str(item['principal_amount']),
                    'interest_amount': str(item['interest_amount']),
                    'total_installment': str(item['total_installment']),
                    'description': item.get('description', ''),
                }
                for item in new_schedule_preview
            ]
            restructure.save()

            if cleaned.get('consolidated_loans'):
                restructure.consolidated_loans.set(cleaned['consolidated_loans'])

        messages.success(
            request,
            f"Restructure proposal #{restructure.pk} for Loan #{loan.pk} submitted with status PENDING."
        )
        return redirect('loans:restructure_detail', pk=restructure.pk)


class LoanRestructureApproveView(TreasurerRequiredMixin, View):
    """Approve and execute a pending loan restructure inside a single transaction."""
    def post(self, request, pk):
        restructure = get_object_or_404(
            LoanRestructure.objects.select_related('loan'),
            pk=pk
        )
        try:
            apply_restructure(restructure, request.user)
            messages.success(
                request,
                f"Loan Restructure #{restructure.pk} approved and applied successfully! "
                f"New schedule generated and previous installments superseded."
            )
        except Exception as e:
            messages.error(request, f"Could not approve restructure: {e}")

        return redirect('loans:restructure_detail', pk=restructure.pk)


class LoanRestructureRejectView(TreasurerRequiredMixin, View):
    """Reject a pending loan restructure without changing schedules or loan terms."""
    def post(self, request, pk):
        restructure = get_object_or_404(
            LoanRestructure.objects.select_related('loan'),
            pk=pk
        )
        form = LoanRestructureRejectForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['rejection_reason']
            try:
                reject_restructure(restructure, request.user, reason)
                messages.info(request, f"Loan Restructure #{restructure.pk} has been rejected.")
            except Exception as e:
                messages.error(request, f"Could not reject restructure: {e}")
        else:
            messages.error(request, "Please provide a valid rejection reason.")

        return redirect('loans:restructure_detail', pk=restructure.pk)


class LoanRestructurePreviewAPIView(TreasurerRequiredMixin, View):
    """JSON endpoint to dynamically preview restructure installments."""
    def post(self, request, loan_pk):
        loan = get_object_or_404(Loan, pk=loan_pk)
        rtype = request.POST.get('restructure_type', 'TERM_EXTENSION')
        
        params = {}
        if request.POST.get('new_term_months'):
            try:
                params['new_term_months'] = int(request.POST.get('new_term_months'))
            except (ValueError, TypeError):
                pass

        if request.POST.get('new_rate'):
            try:
                r_pct = Decimal(request.POST.get('new_rate'))
                params['new_rate'] = str((r_pct / Decimal('100')).quantize(Decimal('0.0001')))
            except Exception:
                pass

        if request.POST.get('moratorium_months'):
            try:
                params['moratorium_months'] = int(request.POST.get('moratorium_months'))
                params['accrue_interest'] = request.POST.get('accrue_interest') in ('true', '1', 'on')
                params['remaining_months'] = int(request.POST.get('remaining_months', loan.duration_months))
            except Exception:
                pass

        try:
            schedule = recalculate_schedule(
                loan=loan,
                restructure_type=rtype,
                params=params,
                as_of_date=timezone.localdate()
            )
            data = [
                {
                    'installment_number': s['installment_number'],
                    'due_date': str(s['due_date']),
                    'principal_amount': float(s['principal_amount']),
                    'interest_amount': float(s['interest_amount']),
                    'total_installment': float(s['total_installment']),
                    'description': s.get('description', ''),
                }
                for s in schedule
            ]
            return JsonResponse({'success': True, 'schedule': data})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)


