from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.db.models import Sum
from decimal import Decimal
from .models import Loan, Collateral, LoanGuarantor, LoanRollover
from .forms import LoanForm, LoanAdjustForm, CollateralForm, LoanGuarantorForm
from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin, MemberAccessMixin, AdminPasswordDeleteMixin
from utils.exports import export_csv, export_pdf


class LoanListView(MemberAccessMixin, ListView):
    model = Loan
    template_name = 'loans/loan_list.html'
    context_object_name = 'loans'
    paginate_by = 20

    def get_queryset(self):
        qs = Loan.objects.select_related('member')
        status = self.request.GET.get('status')
        q = self.request.GET.get('q', '').strip()
        if status == 'unpaid':
            qs = qs.filter(status__in=['active', 'late'])
        elif status:
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(member__name__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        all_loans = Loan.objects.all()
        ctx['total_loans'] = all_loans.aggregate(t=Sum('loan_amount'))['t'] or 0
        ctx['total_interest'] = sum(l.total_payable - l.loan_amount for l in all_loans)
        ctx['total_paid'] = all_loans.aggregate(t=Sum('amount_paid'))['t'] or 0
        ctx['active_count'] = all_loans.filter(status='active').count()
        ctx['cleared_count'] = all_loans.filter(status='cleared').count()
        ctx['late_count'] = all_loans.filter(status='late').count()
        ctx['total_balance'] = sum(l.balance for l in all_loans)
        ctx['current_status'] = self.request.GET.get('status', '')
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
        ctx['all_members'] = Member.objects.all()
        ctx['available_fund_balance'] = get_available_fund_balance()
        return ctx

    def form_valid(self, form):
        from django.db import transaction
        from django.contrib import messages as msg
        from utils.financials import get_available_fund_balance

        # Fund availability check
        loan_amount = form.cleaned_data.get('loan_amount')
        available = get_available_fund_balance()
        if loan_amount and loan_amount > available:
            msg.error(
                self.request,
                f'Loan amount KES {loan_amount:,.2f} exceeds the available fund balance '
                f'of KES {available:,.2f}. Please reduce the loan amount or wait for more funds.'
            )
            return self.form_invalid(form)

        with transaction.atomic():
            response = super().form_valid(form)
            loan = self.object
            guarantor_ids = self.request.POST.getlist('guarantor_ids[]')
            guarantor_amounts = self.request.POST.getlist('guarantor_amounts[]')

            member_contrib = loan.member.total_contributions() or Decimal('0')
            shortfall = max(loan.loan_amount - member_contrib, Decimal('0'))
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
                    if g != loan.member:
                        LoanGuarantor.objects.get_or_create(
                            loan=loan, guarantor=g,
                            defaults={'amount_guaranteed': amt}
                        )
                        total_guaranteed += amt
                except (M.DoesNotExist, ValueError, TypeError) as e:
                    errors.append(f"Could not process guarantor #{gid}: {e}")

            if shortfall > 0 and total_guaranteed < shortfall:
                # Roll back the whole transaction
                transaction.set_rollback(True)
                gap = shortfall - total_guaranteed
                err = f"Guarantor coverage insufficient. Need KES {shortfall:,.2f}, got KES {total_guaranteed:,.2f}. Shortfall: KES {gap:,.2f}."
                if errors:
                    err += " Also: " + " | ".join(errors)
                msg.error(self.request, err)
                return self.form_invalid(form)

            for e in errors:
                msg.warning(self.request, e)

        return response


class LoanUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Loan
    form_class = LoanAdjustForm
    template_name = 'loans/loan_form.html'
    success_url = reverse_lazy('loans:list')
    success_message = "Loan updated."

    def get_initial(self):
        initial = super().get_initial()
        # Pre-populate duration_months as string so ChoiceField matches correctly
        initial['duration_months'] = str(self.object.duration_months)
        return initial

    def form_valid(self, form):
        loan = form.save(commit=False)
        from decimal import Decimal
        from .models import INTEREST_RATE
        import calendar
        from django.utils import timezone as tz

        # Apply the manually-set penalty months from the adjust form
        loan.late_penalty_months = form.cleaned_data.get('late_penalty_months', 0)

        principal = Decimal(str(loan.loan_amount))
        loan.interest_amount = (principal * INTEREST_RATE).quantize(Decimal('0.01'))
        loan.late_penalty_per_month = loan.interest_amount
        accumulated = loan.late_penalty_per_month * loan.late_penalty_months
        loan.total_payable = (principal + loan.interest_amount + accumulated).quantize(Decimal('0.01'))

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


class LoanDetailView(MemberAccessMixin, DetailView):
    model = Loan
    template_name = 'loans/loan_detail.html'
    context_object_name = 'loan'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['payments'] = self.object.payment_set.select_related('member').all()
        return ctx


class LoanCalculatorView(MemberAccessMixin, View):
    """AJAX endpoint — returns flat interest preview using the configured rate."""
    def get(self, request):
        try:
            from decimal import Decimal
            from .models import INTEREST_RATE
            amount = Decimal(request.GET.get('amount', '0'))
            months = int(request.GET.get('months', '1'))
            if amount <= 0 or months <= 0:
                raise ValueError
            interest = (amount * INTEREST_RATE).quantize(Decimal('0.01'))
            total_payable = amount + interest
            return JsonResponse({
                'total_interest': str(interest),
                'total_payable': str(total_payable),
                'rate_percent': str(int(INTEREST_RATE * 100)),
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
        if loan.status == 'cleared':
            from django.contrib import messages
            messages.error(request, "This loan is already cleared and cannot be rolled over.")
            return redirect('loans:detail', pk=pk)
        from decimal import Decimal
        from .models import INTEREST_RATE
        from utils.financials import get_available_fund_balance
        outstanding = loan.balance
        new_interest = (outstanding * INTEREST_RATE).quantize(Decimal('0.01'))
        new_total = outstanding + new_interest
        available = get_available_fund_balance()
        return render(request, 'loans/loan_rollover_confirm.html', {
            'loan': loan,
            'outstanding': outstanding,
            'new_interest': new_interest,
            'new_total': new_total,
            'duration_choices': range(1, 25),
            'available_fund_balance': available,
        })

    def post(self, request, pk):
        loan = Loan.objects.get(pk=pk)
        if loan.status == 'cleared':
            from django.contrib import messages
            messages.error(request, "This loan is already cleared.")
            return redirect('loans:detail', pk=pk)
        from utils.financials import get_available_fund_balance
        available = get_available_fund_balance()
        if loan.balance > available:
            from django.contrib import messages
            messages.error(
                request,
                f'Rollover rejected. The outstanding balance of KES {loan.balance:,.2f} '
                f'exceeds the available fund balance of KES {available:,.2f}.'
            )
            return redirect('loans:detail', pk=pk)
        duration = int(request.POST.get('duration_months', loan.duration_months))
        loan.do_rollover(duration_months=duration)
        from django.contrib import messages
        messages.success(request, f"Loan #{loan.pk} rolled over. New balance: KES {loan.total_payable:,.2f}")
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
        ctx['guarantors'] = paginator.get_page(page)
        ctx['total_count'] = qs.count()
        return ctx


class LoanExportView(MemberAccessMixin, View):
    def get(self, request):
        format_type = request.GET.get('format', 'csv')
        qs = Loan.objects.select_related('member')
        status = request.GET.get('status', '').strip()
        q = request.GET.get('q', '').strip()
        if status == 'unpaid':
            qs = qs.filter(status__in=['active', 'late'])
        elif status:
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(member__name__icontains=q)

        fields = [
            ('member.name', 'Member'),
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
