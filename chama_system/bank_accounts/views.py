from decimal import Decimal

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView

from .models import BankAccount, BankBalance
from .forms import BankAccountForm, BankBalanceForm, BankTopUpForm, BankOpeningBalanceForm
from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin, MemberAccessMixin, AdminPasswordDeleteMixin


class BankAccountListView(MemberAccessMixin, ListView):
    model = BankAccount
    template_name = 'bank_accounts/list.html'
    context_object_name = 'accounts'

    def get_queryset(self):
        return BankAccount.objects.prefetch_related('balances').order_by('bank_name', 'account_name')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        accounts = list(ctx['accounts'])
        ctx['total_bank_balance'] = sum(a.current_balance for a in accounts if a.is_active)
        ctx['general_bank_balance'] = sum(a.current_balance for a in accounts if a.fund_type == BankAccount.FUND_TYPE_GENERAL and a.is_active)
        ctx['welfare_bank_balance'] = sum(a.current_balance for a in accounts if a.fund_type == BankAccount.FUND_TYPE_WELFARE and a.is_active)
        ctx['reg_bank_balance'] = sum(a.current_balance for a in accounts if a.fund_type == BankAccount.FUND_TYPE_REGISTRATION and a.is_active)
        ctx['active_count'] = sum(1 for a in accounts if a.is_active)
        return ctx


def _get_bank_form_context(extra=None):
    accounts = list(BankAccount.objects.all().order_by('-is_active', 'bank_name', 'account_name'))
    ctx = {
        'total_bank_balance': sum(a.current_balance for a in accounts if a.is_active),
        'general_bank_balance': sum(a.current_balance for a in accounts if a.fund_type == BankAccount.FUND_TYPE_GENERAL and a.is_active),
        'welfare_bank_balance': sum(a.current_balance for a in accounts if a.fund_type == BankAccount.FUND_TYPE_WELFARE and a.is_active),
        'active_count': sum(1 for a in accounts if a.is_active),
        'accounts_count': len(accounts),
        'existing_accounts': accounts[:5],
    }
    if extra:
        ctx.update(extra)
    return ctx


class BankAccountCreateView(TreasurerRequiredMixin, View):
    """Create account + optionally set opening balance in one step."""
    template_name = 'bank_accounts/form.html'

    def get(self, request):
        return render(request, self.template_name, _get_bank_form_context({
            'account_form': BankAccountForm(),
            'opening_form': BankOpeningBalanceForm(),
        }))

    def post(self, request):
        account_form  = BankAccountForm(request.POST)
        opening_form  = BankOpeningBalanceForm(request.POST)

        if account_form.is_valid() and opening_form.is_valid():
            with transaction.atomic():
                account = account_form.save()
                opening_bal = opening_form.cleaned_data['opening_balance']
                if opening_bal > 0:
                    BankBalance.objects.create(
                        account=account,
                        balance=opening_bal,
                        topup_amount=opening_bal,
                        transaction_type=BankBalance.TYPE_OPENING,
                        recorded_on=opening_form.cleaned_data['date'],
                        notes=opening_form.cleaned_data.get('notes', '') or 'Opening balance',
                        recorded_by=request.user,
                    )
            messages.success(request, f'Bank account "{account}" added successfully.')
            return redirect('bank_accounts:detail', pk=account.pk)

        return render(request, self.template_name, _get_bank_form_context({
            'account_form': account_form,
            'opening_form': opening_form,
        }))


class BankAccountUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = BankAccount
    form_class = BankAccountForm
    template_name = 'bank_accounts/form.html'
    success_url = reverse_lazy('bank_accounts:list')
    success_message = "Bank account updated."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Expose as account_form so the template uses the same variable name as create view
        ctx['account_form'] = ctx['form']
        ctx['is_edit'] = True
        return _get_bank_form_context(ctx)


class BankAccountDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = BankAccount
    template_name = 'bank_accounts/confirm_delete.html'
    success_url = reverse_lazy('bank_accounts:list')


class BankAccountDetailView(MemberAccessMixin, DetailView):
    model = BankAccount
    template_name = 'bank_accounts/detail.html'
    context_object_name = 'account'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # All transactions ordered oldest→newest for running total display
        entries = list(self.object.balances.order_by('recorded_on', 'created_at'))
        ctx['entries'] = list(reversed(entries))  # newest first for table
        ctx['topup_form']  = BankTopUpForm()
        # Compute totals
        from django.db.models import Sum
        ctx['total_topups']     = (
            self.object.balances.filter(
                transaction_type__in=[BankBalance.TYPE_OPENING, BankBalance.TYPE_TOPUP]
            ).aggregate(t=Sum('topup_amount'))['t'] or Decimal('0.00')
        )
        ctx['total_deductions'] = (
            self.object.balances.filter(transaction_type=BankBalance.TYPE_DEDUCTION)
            .aggregate(t=Sum('topup_amount'))['t'] or Decimal('0.00')
        )
        return ctx


class BankTopUpView(TreasurerRequiredMixin, View):
    """Record a top-up (deposit) for a bank account."""

    def post(self, request, account_pk):
        account = get_object_or_404(BankAccount, pk=account_pk)
        form = BankTopUpForm(request.POST)

        if form.is_valid():
            amount       = form.cleaned_data['amount']
            date         = form.cleaned_data['date']
            notes        = form.cleaned_data.get('notes', '')
            current_bal  = account.current_balance
            new_balance  = current_bal + amount

            BankBalance.objects.create(
                account=account,
                balance=new_balance,
                topup_amount=amount,
                transaction_type=BankBalance.TYPE_TOPUP,
                recorded_on=date,
                notes=notes or f'Top-up of KES {amount:,.2f}',
                recorded_by=request.user,
            )
            messages.success(
                request,
                f'KES {amount:,.2f} top-up recorded. New balance: KES {new_balance:,.2f}.'
            )
        else:
            for field_errors in form.errors.values():
                for err in field_errors:
                    messages.error(request, err)

        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('bank_accounts:detail', pk=account_pk)


class BankOpeningBalanceView(TreasurerRequiredMixin, View):
    """Set or update the opening balance for an account."""

    def post(self, request, account_pk):
        account = get_object_or_404(BankAccount, pk=account_pk)
        form = BankOpeningBalanceForm(request.POST)

        if form.is_valid():
            amount = form.cleaned_data['opening_balance']
            date   = form.cleaned_data['date']
            notes  = form.cleaned_data.get('notes', '') or 'Opening balance'
            # Remove existing opening entry if any, then recreate
            with transaction.atomic():
                account.balances.filter(
                    transaction_type=BankBalance.TYPE_OPENING
                ).delete()
                BankBalance.objects.create(
                    account=account,
                    balance=amount,
                    topup_amount=amount,
                    transaction_type=BankBalance.TYPE_OPENING,
                    recorded_on=date,
                    notes=notes,
                    recorded_by=request.user,
                )
            messages.success(request, f'Opening balance set to KES {amount:,.2f}.')
        else:
            messages.error(request, 'Invalid opening balance.')

        return redirect('bank_accounts:detail', pk=account_pk)


class BankBalanceCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    """Legacy snapshot entry — kept for backward compatibility."""
    model = BankBalance
    form_class = BankBalanceForm
    template_name = 'bank_accounts/balance_form.html'
    success_message = "Balance snapshot recorded."

    def get_account(self):
        return get_object_or_404(BankAccount, pk=self.kwargs['account_pk'])

    def form_valid(self, form):
        form.instance.account          = self.get_account()
        form.instance.transaction_type = BankBalance.TYPE_SNAPSHOT
        form.instance.recorded_by      = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('bank_accounts:detail', kwargs={'pk': self.kwargs['account_pk']})

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['account'] = self.get_account()
        return ctx


class BankBalanceDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = BankBalance
    template_name = 'bank_accounts/balance_confirm_delete.html'

    def get_success_url(self):
        return reverse_lazy('bank_accounts:detail', kwargs={'pk': self.object.account_id})


class BulkBankAccountDeleteView(AdminRequiredMixin, View):
    """Bulk delete multiple bank accounts (requires admin password)."""
    
    def post(self, request):
        account_ids = request.POST.get('account_ids', '').split(',')
        account_ids = [int(id) for id in account_ids if id.strip()]
        
        if not account_ids:
            messages.error(request, "No accounts selected.")
            return redirect('bank_accounts:list')
        
        # Redirect to confirmation page with selected IDs
        accounts = BankAccount.objects.filter(pk__in=account_ids)
        
        if request.POST.get('confirm') == 'true':
            # Process actual deletion with password confirmation
            password = request.POST.get('admin_password', '')
            reason = request.POST.get('delete_reason', '').strip()
            
            if not reason:
                return render(request, 'bank_accounts/bulk_delete_confirm.html', {
                    'accounts': accounts,
                    'error': 'Deletion reason is required.',
                    'account_ids': ','.join(str(id) for id in account_ids),
                })
            
            if not request.user.check_password(password):
                return render(request, 'bank_accounts/bulk_delete_confirm.html', {
                    'accounts': accounts,
                    'error': 'Incorrect password. Deletion cancelled.',
                    'account_ids': ','.join(str(id) for id in account_ids),
                })
            
            # Delete accounts
            from recycle_bin.models import DeletedRecord
            from recycle_bin.serializer import serialize_instance
            
            deleted_count = 0
            with transaction.atomic():
                for account in accounts:
                    try:
                        # Save to recycle bin
                        data = serialize_instance(account)
                        DeletedRecord.objects.create(
                            app_label=account._meta.app_label,
                            model_name=account._meta.model_name,
                            object_id=str(account.pk),
                            object_repr=str(account)[:300],
                            data=data,
                            delete_reason=reason,
                            deleted_by=request.user,
                        )
                        # Delete account (will cascade-delete associated BankBalance entries)
                        account.delete()
                        deleted_count += 1
                    except Exception as e:
                        messages.error(request, f"Error deleting {account.account_name}: {str(e)[:50]}")
            
            if deleted_count:
                messages.success(request, f"{deleted_count} account(s) deleted successfully.")
            
            return redirect('bank_accounts:list')
        
        # Show confirmation page
        return render(request, 'bank_accounts/bulk_delete_confirm.html', {
            'accounts': accounts,
            'account_ids': ','.join(str(id) for id in account_ids),
        })
