from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.db.models import Sum, Count, Q
from decimal import Decimal
from .models import Loan, Collateral, LoanGuarantor, LoanRollover
from .forms import LoanForm, CollateralForm, LoanGuarantorForm
from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin


class LoanListView(LoginRequiredMixin, ListView):
    model = Loan
    template_name = 'loans/loan_list.html'
    context_object_name = 'loans'
    paginate_by = 20

    def get_queryset(self):
        qs = Loan.objects.select_related('member')
        status = self.request.GET.get('status')
        q = self.request.GET.get('q', '').strip()
        if status:
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(member__name__icontains=q)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_loans'] = Loan.objects.aggregate(t=Sum('loan_amount'))['t'] or 0
        ctx['total_interest'] = Loan.objects.aggregate(t=Sum('interest_amount'))['t'] or 0
        ctx['active_count'] = Loan.objects.filter(status='active').count()
        ctx['cleared_count'] = Loan.objects.filter(status='cleared').count()
        ctx['late_count'] = Loan.objects.filter(status='late').count()
        ctx['total_balance'] = sum(l.balance for l in Loan.objects.all())
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
        ctx['all_members'] = Member.objects.all()
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        loan = self.object
        guarantor_ids = self.request.POST.getlist('guarantor_ids[]')
        guarantor_amounts = self.request.POST.getlist('guarantor_amounts[]')

        shortfall = max(float(loan.loan_amount) - float(loan.member.total_contributions()), 0)
        total_guaranteed = 0.0
        errors = []

        for gid, amt_str in zip(guarantor_ids, guarantor_amounts):
            try:
                from members.models import Member as M
                g = M.objects.get(pk=gid)
                amt = float(amt_str or 0)
                if amt <= 0:
                    continue
                g_contributions = float(g.total_contributions() or 0)
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
            except Exception:
                pass

        if shortfall > 0 and total_guaranteed < shortfall:
            # delete the loan we just created and report the error
            loan.delete()
            from django.contrib import messages
            gap = shortfall - total_guaranteed
            msg = f"Guarantor coverage is insufficient. Need KES {shortfall:,.2f} covered, got KES {total_guaranteed:,.2f}. Shortfall: KES {gap:,.2f}."
            if errors:
                msg += " Also: " + " | ".join(errors)
            messages.error(self.request, msg)
            return self.form_invalid(form)

        if errors:
            from django.contrib import messages
            for e in errors:
                messages.warning(self.request, e)

        return response


class LoanUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Loan
    form_class = LoanForm
    template_name = 'loans/loan_form.html'
    success_url = reverse_lazy('loans:list')
    success_message = "Loan updated."

    def get_success_url(self):
        return reverse_lazy('loans:detail', kwargs={'pk': self.object.pk})


class LoanDeleteView(AdminRequiredMixin, DeleteView):
    model = Loan
    template_name = 'loans/loan_confirm_delete.html'
    success_url = reverse_lazy('loans:list')


class LoanDetailView(LoginRequiredMixin, DetailView):
    model = Loan
    template_name = 'loans/loan_detail.html'
    context_object_name = 'loan'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['payments'] = self.object.payment_set.select_related('member').all()
        return ctx


class LoanCalculatorView(LoginRequiredMixin, View):
    """AJAX endpoint — returns flat 10% interest preview."""
    def get(self, request):
        try:
            from decimal import Decimal
            amount = Decimal(request.GET.get('amount', '0'))
            months = int(request.GET.get('months', '1'))
            if amount <= 0 or months <= 0:
                raise ValueError
            from .models import INTEREST_RATE
            interest = (amount * INTEREST_RATE).quantize(Decimal('0.01'))
            total_payable = amount + interest
            return JsonResponse({
                'total_interest': str(interest),
                'total_payable': str(total_payable),
                'rate_percent': '10',
            })
        except Exception:
            return JsonResponse({'error': 'Invalid input'}, status=400)


class MemberContributionCheckView(LoginRequiredMixin, View):
    """AJAX — returns member's total contributions and eligible guarantors."""
    def get(self, request):
        from members.models import Member
        member_id = request.GET.get('member_id')
        loan_amount = request.GET.get('amount', '0')
        try:
            member = Member.objects.get(pk=member_id)
            total_contributions = float(member.total_contributions() or 0)
            loan_amount = float(loan_amount or 0)
            shortfall = max(loan_amount - total_contributions, 0)
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
                    'max_guarantee': float(m.total_contributions() or 0),  # can only guarantee up to their contributions
                }
                for m in eligible
            ]
            return JsonResponse({
                'total_contributions': total_contributions,
                'needs_guarantor': needs_guarantor,
                'shortfall': shortfall,          # coverage target is the shortfall, not the full loan
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


class CollateralDeleteView(AdminRequiredMixin, DeleteView):
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


class GuarantorDeleteView(TreasurerRequiredMixin, DeleteView):
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
        outstanding = loan.balance
        new_interest = (outstanding * INTEREST_RATE).quantize(Decimal('0.01'))
        new_total = outstanding + new_interest
        return render(request, 'loans/loan_rollover_confirm.html', {
            'loan': loan,
            'outstanding': outstanding,
            'new_interest': new_interest,
            'new_total': new_total,
            'duration_choices': range(1, 25),
        })

    def post(self, request, pk):
        loan = Loan.objects.get(pk=pk)
        if loan.status == 'cleared':
            from django.contrib import messages
            messages.error(request, "This loan is already cleared.")
            return redirect('loans:detail', pk=pk)
        duration = int(request.POST.get('duration_months', loan.duration_months))
        loan.do_rollover(duration_months=duration)
        from django.contrib import messages
        messages.success(request, f"Loan #{loan.pk} rolled over. New balance: KES {loan.total_payable:,.2f}")
        return redirect('loans:detail', pk=pk)


class GuarantorsReportView(LoginRequiredMixin, TemplateView):
    template_name = 'loans/guarantors_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['guarantors'] = (
            LoanGuarantor.objects
            .select_related('guarantor', 'loan__member')
            .order_by('guarantor__name')
        )
        return ctx
