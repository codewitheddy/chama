import csv
from decimal import Decimal
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView

from accounts.mixins import MemberAccessMixin, TreasurerRequiredMixin, AdminRequiredMixin
from bank_accounts.models import BankAccount, BankBalance
from contributions.models import Contribution
from expenses.models import Expense
from investments.models import Investment, InvestmentReturn, InvestmentWithdrawal
from loans.models import Loan
from meetings.models import Meeting
from members.models import Member, RegistrationFeePayment
from money_movement.forms import (
    BankReconciliationForm,
    CashReconciliationForm,
    MoneyTransferForm,
    TransferReversalForm,
)
from money_movement.models import (
    BankReconciliation,
    CashReconciliation,
    MoneyAccount,
    MoneyTransfer,
)
from money_movement.services import get_account_balances, get_funds_position
from other_income.models import OtherIncome
from payments.models import Payment
from penalties.models import Penalty
from utils.exports import _get_document_footer, _get_group_name, export_csv


class MoneyMovementDashboardView(MemberAccessMixin, TemplateView):
    template_name = 'money_movement/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        position = get_funds_position()
        ctx.update(position)

        # Accounts breakdown
        MoneyAccount.get_or_create_default_cash()
        MoneyAccount.get_or_create_default_mpesa()
        MoneyAccount.get_or_create_default_investments()
        MoneyAccount.sync_bank_accounts()

        ctx['accounts'] = MoneyAccount.objects.filter(is_active=True)
        ctx['account_balances'] = get_account_balances()

        # Recent and Pending Transfers
        ctx['recent_transfers'] = MoneyTransfer.objects.select_related(
            'from_account', 'to_account', 'recorded_by', 'approved_by'
        ).order_by('-transfer_date', '-recorded_at')[:10]

        ctx['pending_transfers'] = MoneyTransfer.objects.filter(
            status=MoneyTransfer.STATUS_PENDING
        ).select_related('from_account', 'to_account', 'recorded_by')

        # Recent reconciliations
        ctx['recent_cash_recons'] = CashReconciliation.objects.select_related('reconciled_by')[:3]
        ctx['recent_bank_recons'] = BankReconciliation.objects.select_related('bank_account', 'reconciled_by')[:3]

        return ctx


class MoneyTransferListView(MemberAccessMixin, ListView):
    model = MoneyTransfer
    template_name = 'money_movement/transfer_list.html'
    context_object_name = 'transfers'
    paginate_by = 15

    def get_queryset(self):
        qs = MoneyTransfer.objects.select_related(
            'from_account', 'to_account', 'recorded_by', 'approved_by', 'reversal_of'
        ).order_by('-transfer_date', '-recorded_at')

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(reference__icontains=q) |
                Q(deposited_by__icontains=q) |
                Q(notes__icontains=q) |
                Q(from_account__name__icontains=q) |
                Q(to_account__name__icontains=q)
            )

        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)

        transfer_type = self.request.GET.get('type', '').strip()
        if transfer_type:
            qs = qs.filter(transfer_type=transfer_type)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['selected_type'] = self.request.GET.get('type', '')
        ctx['status_choices'] = MoneyTransfer.STATUS_CHOICES
        ctx['type_choices'] = MoneyTransfer.TRANSFER_TYPE_CHOICES
        ctx['pending_count'] = MoneyTransfer.objects.filter(status=MoneyTransfer.STATUS_PENDING).count()
        return ctx


class MoneyTransferCreateView(TreasurerRequiredMixin, CreateView):
    model = MoneyTransfer
    form_class = MoneyTransferForm
    template_name = 'money_movement/transfer_form.html'

    def get_initial(self):
        initial = super().get_initial()
        initial['transfer_date'] = timezone.localdate()
        prefill_type = self.request.GET.get('type', '')
        if prefill_type:
            initial['transfer_type'] = prefill_type
            cash_acc = MoneyAccount.get_or_create_default_cash()
            mpesa_acc = MoneyAccount.get_or_create_default_mpesa()
            first_bank = MoneyAccount.objects.filter(account_type=MoneyAccount.TYPE_BANK, is_active=True).first()

            if prefill_type == MoneyTransfer.TYPE_CASH_TO_BANK:
                initial['from_account'] = cash_acc
                if first_bank:
                    initial['to_account'] = first_bank
            elif prefill_type == MoneyTransfer.TYPE_BANK_TO_CASH:
                if first_bank:
                    initial['from_account'] = first_bank
                initial['to_account'] = cash_acc
            elif prefill_type == MoneyTransfer.TYPE_MPESA_TO_CASH:
                initial['from_account'] = mpesa_acc
                initial['to_account'] = cash_acc
            elif prefill_type == MoneyTransfer.TYPE_MPESA_TO_BANK:
                initial['from_account'] = mpesa_acc
                if first_bank:
                    initial['to_account'] = first_bank
        return initial

    def form_valid(self, form):
        transfer = form.save(commit=False)
        transfer.recorded_by = self.request.user
        require_approval = form.cleaned_data.get('require_approval', False)

        with transaction.atomic():
            if require_approval:
                transfer.status = MoneyTransfer.STATUS_PENDING
                transfer.save()
                messages.warning(
                    self.request,
                    f"Transfer #{transfer.pk} recorded as PENDING. Second officer approval is required before funds are posted."
                )
            else:
                transfer.status = MoneyTransfer.STATUS_APPROVED
                transfer.approved_by = self.request.user
                transfer.approved_at = timezone.now()
                transfer.save()
                transfer._sync_with_bank_ledger()
                messages.success(
                    self.request,
                    f"Transfer of KES {transfer.amount:,.2f} from {transfer.from_account.name} to {transfer.to_account.name} posted successfully."
                )

        return redirect('money_movement:transfer_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['account_balances'] = get_account_balances()
        ctx['funds_position'] = get_funds_position()
        return ctx


class MoneyTransferApproveView(TreasurerRequiredMixin, View):
    def post(self, request, pk):
        transfer = get_object_or_404(MoneyTransfer, pk=pk)
        if transfer.status != MoneyTransfer.STATUS_PENDING:
            messages.error(request, "This transfer is not pending approval.")
            return redirect('money_movement:transfer_list')

        # Check balance again at approval time
        balances = get_account_balances()
        available = balances.get(transfer.from_account_id, Decimal('0.00'))
        if transfer.amount > available:
            messages.error(
                request,
                f"Cannot approve: Insufficient funds in {transfer.from_account.name}. "
                f"Available: KES {available:,.2f}, Required: KES {transfer.amount:,.2f}."
            )
            return redirect('money_movement:transfer_list')

        transfer.approve(request.user)
        messages.success(
            request,
            f"Transfer #{transfer.pk} of KES {transfer.amount:,.2f} approved and posted by {request.user.get_full_name() or request.user.username}."
        )
        return redirect('money_movement:transfer_list')


class MoneyTransferRejectView(TreasurerRequiredMixin, View):
    def post(self, request, pk):
        transfer = get_object_or_404(MoneyTransfer, pk=pk)
        if transfer.status != MoneyTransfer.STATUS_PENDING:
            messages.error(request, "This transfer is not pending.")
            return redirect('money_movement:transfer_list')

        reason = request.POST.get('rejection_reason', 'Rejected by second officer').strip()
        transfer.reject(request.user, reason)
        messages.info(request, f"Transfer #{transfer.pk} was rejected.")
        return redirect('money_movement:transfer_list')


class MoneyTransferReverseView(TreasurerRequiredMixin, View):
    def post(self, request, pk):
        transfer = get_object_or_404(MoneyTransfer, pk=pk)
        reason = request.POST.get('reversal_reason', '').strip()

        if not reason:
            messages.error(request, "A detailed explanation reason is required to reverse a completed transfer.")
            return redirect('money_movement:transfer_list')

        try:
            reversal = transfer.create_reversal(request.user, reason)
            messages.success(
                request,
                f"Transfer #{transfer.pk} reversed successfully. Reversal Entry #{reversal.pk} has been posted."
            )
        except ValidationError as e:
            messages.error(request, str(e))

        return redirect('money_movement:transfer_list')


# ─────────────────────────────────────────────────────────────────
# RECONCILIATIONS
# ─────────────────────────────────────────────────────────────────

class CashReconciliationView(TreasurerRequiredMixin, TemplateView):
    template_name = 'money_movement/cash_reconciliation.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        position = get_funds_position()
        ctx['system_cash'] = position['cash_in_hand']
        ctx['form'] = CashReconciliationForm()
        ctx['history'] = CashReconciliation.objects.select_related('reconciled_by').order_by('-reconciliation_date', '-created_at')[:20]
        return ctx

    def post(self, request, *args, **kwargs):
        form = CashReconciliationForm(request.POST)
        position = get_funds_position()
        system_cash = position['cash_in_hand']

        if form.is_valid():
            recon = form.save(commit=False)
            recon.reconciled_by = request.user
            recon.system_cash = system_cash

            # Compute actual cash from denominations
            actual = (
                Decimal(str(recon.notes_1000 * 1000)) +
                Decimal(str(recon.notes_500 * 500)) +
                Decimal(str(recon.notes_200 * 200)) +
                Decimal(str(recon.notes_100 * 100)) +
                Decimal(str(recon.notes_50 * 50)) +
                recon.coins_amount
            )
            recon.actual_cash = actual
            recon.variance = actual - system_cash

            if abs(recon.variance) < Decimal('0.01'):
                recon.status = CashReconciliation.STATUS_BALANCED
            elif recon.variance > 0:
                recon.status = CashReconciliation.STATUS_SURPLUS
            else:
                recon.status = CashReconciliation.STATUS_SHORTAGE

            recon.save()
            messages.success(
                request,
                f"Cash count recorded: Physical KES {actual:,.2f} vs System KES {system_cash:,.2f}. Variance: KES {recon.variance:,.2f}."
            )
            return redirect('money_movement:reconcile_cash')

        ctx = self.get_context_data(**kwargs)
        ctx['form'] = form
        return self.render_to_response(ctx)


class BankReconciliationView(TreasurerRequiredMixin, TemplateView):
    template_name = 'money_movement/bank_reconciliation.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        bank_id = self.request.GET.get('bank_id', '')
        selected_bank = None
        if bank_id:
            selected_bank = BankAccount.objects.filter(pk=bank_id, is_active=True).first()
        if not selected_bank:
            selected_bank = BankAccount.objects.filter(is_active=True).first()

        ctx['selected_bank'] = selected_bank
        ctx['banks'] = BankAccount.objects.filter(is_active=True)
        ctx['form'] = BankReconciliationForm(initial={'bank_account': selected_bank} if selected_bank else None)

        if selected_bank:
            ctx['ledger_balance'] = selected_bank.current_balance
            ctx['recent_transactions'] = selected_bank.balances.order_by('-recorded_on', '-created_at')[:25]
            ctx['history'] = selected_bank.reconciliations.select_related('reconciled_by').order_by('-statement_date', '-created_at')[:15]
            ctx['direct_other_incomes'] = selected_bank.other_incomes.select_related('reconciled_by').order_by('-date')[:15]
        else:
            ctx['ledger_balance'] = Decimal('0.00')
            ctx['recent_transactions'] = []
            ctx['history'] = []
            ctx['direct_other_incomes'] = []

        return ctx

    def post(self, request, *args, **kwargs):
        form = BankReconciliationForm(request.POST)
        if form.is_valid():
            recon = form.save(commit=False)
            recon.reconciled_by = request.user
            recon.ledger_balance = recon.bank_account.current_balance
            recon.variance = recon.statement_balance - recon.ledger_balance

            if abs(recon.variance) < Decimal('0.01'):
                recon.status = BankReconciliation.STATUS_RECONCILED
            else:
                recon.status = BankReconciliation.STATUS_UNRECONCILED

            recon.save()
            messages.success(
                request,
                f"Bank statement reconciliation recorded for {recon.bank_account.bank_name}. Variance: KES {recon.variance:,.2f}."
            )
            return redirect(f"{request.path}?bank_id={recon.bank_account_id}")

        ctx = self.get_context_data(**kwargs)
        ctx['form'] = form
        return self.render_to_response(ctx)


# ─────────────────────────────────────────────────────────────────
# REPORTS
# ─────────────────────────────────────────────────────────────────

class MeetingSummaryReportView(MemberAccessMixin, TemplateView):
    template_name = 'money_movement/reports/meeting_summary.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        meeting_id = self.request.GET.get('meeting_id', '')
        selected_meeting = None
        if meeting_id:
            selected_meeting = Meeting.objects.filter(pk=meeting_id).first()
        if not selected_meeting:
            selected_meeting = Meeting.objects.order_by('-date').first()

        ctx['meetings'] = Meeting.objects.order_by('-date')[:30]
        ctx['selected_meeting'] = selected_meeting

        if selected_meeting:
            m_date = selected_meeting.date

            # Inflows by mode on meeting date
            cash_contrib = Contribution.objects.filter(date=m_date, payment_type='cash').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
            mpesa_contrib = Contribution.objects.filter(date=m_date, payment_type='mpesa').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

            cash_repay = Payment.objects.filter(date=m_date, payment_type='cash').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
            mpesa_repay = Payment.objects.filter(date=m_date, payment_type='mpesa').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

            cash_pen = Penalty.objects.filter(paid=True, paid_date=m_date, payment_type='cash').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
            mpesa_pen = Penalty.objects.filter(paid=True, paid_date=m_date, payment_type='mpesa').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

            cash_reg = RegistrationFeePayment.objects.filter(payment_date=m_date, payment_method='cash').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
            mpesa_reg = RegistrationFeePayment.objects.filter(payment_date=m_date, payment_method='mpesa').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

            total_cash_collected = cash_contrib + cash_repay + cash_pen + cash_reg
            total_mpesa_collected = mpesa_contrib + mpesa_repay + mpesa_pen + mpesa_reg
            total_meeting_collected = total_cash_collected + total_mpesa_collected

            # Disbursements & movements on meeting date
            loans_cash = Loan.objects.filter(date_taken=m_date, fund_source='group_funds').aggregate(s=Sum('loan_amount'))['s'] or Decimal('0.00')
            loans_bank = Loan.objects.filter(date_taken=m_date, fund_source='bank_account').aggregate(s=Sum('loan_amount'))['s'] or Decimal('0.00')
            expenses_paid = Expense.objects.filter(date=m_date).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

            # Cash Banked on meeting date
            cash_banked = MoneyTransfer.objects.filter(
                transfer_date=m_date,
                status=MoneyTransfer.STATUS_APPROVED,
                transfer_type=MoneyTransfer.TYPE_CASH_TO_BANK
            ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

            net_cash_remaining = total_cash_collected - loans_cash - expenses_paid - cash_banked

            ctx.update({
                'cash_contrib': cash_contrib,
                'mpesa_contrib': mpesa_contrib,
                'cash_repay': cash_repay,
                'mpesa_repay': mpesa_repay,
                'cash_pen': cash_pen,
                'mpesa_pen': mpesa_pen,
                'cash_reg': cash_reg,
                'mpesa_reg': mpesa_reg,
                'total_cash_collected': total_cash_collected,
                'total_mpesa_collected': total_mpesa_collected,
                'total_meeting_collected': total_meeting_collected,
                'loans_cash': loans_cash,
                'loans_bank': loans_bank,
                'expenses_paid': expenses_paid,
                'cash_banked': cash_banked,
                'net_cash_remaining': net_cash_remaining,
            })

        return ctx


class CashBookReportView(MemberAccessMixin, TemplateView):
    template_name = 'money_movement/reports/cash_book.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        year = self.request.GET.get('year', '')
        today = timezone.localdate()
        ctx['years'] = list(range(today.year - 4, today.year + 1))
        ctx['selected_year'] = year

        # Build chronological cash inflows and outflows
        entries = []
        c_qs = Contribution.objects.filter(payment_type='cash')
        p_qs = Payment.objects.filter(payment_type='cash')
        pen_qs = Penalty.objects.filter(paid=True, payment_type='cash')
        rf_qs = RegistrationFeePayment.objects.filter(payment_method='cash')
        exp_qs = Expense.objects.filter(fund_source__in=['group_funds', 'registration_fees'])
        loan_qs = Loan.objects.filter(fund_source='group_funds')
        tr_qs = MoneyTransfer.objects.filter(status=MoneyTransfer.STATUS_APPROVED).filter(
            Q(from_account__account_type=MoneyAccount.TYPE_CASH) |
            Q(to_account__account_type=MoneyAccount.TYPE_CASH)
        )
        other_inc_qs = OtherIncome.objects.filter(payment_method=OtherIncome.PAYMENT_CASH)
        topup_qs = BankBalance.objects.filter(transaction_type=BankBalance.TYPE_TOPUP).exclude(notes__contains='Transfer #')
        inv_qs = Investment.objects.filter(fund_source='cash')

        if year:
            c_qs = c_qs.filter(date__year=year)
            p_qs = p_qs.filter(date__year=year)
            pen_qs = pen_qs.filter(paid_date__year=year)
            rf_qs = rf_qs.filter(payment_date__year=year)
            exp_qs = exp_qs.filter(date__year=year)
            loan_qs = loan_qs.filter(date_taken__year=year)
            tr_qs = tr_qs.filter(transfer_date__year=year)
            other_inc_qs = other_inc_qs.filter(date__year=year)
            topup_qs = topup_qs.filter(recorded_on__year=year)
            inv_qs = inv_qs.filter(start_date__year=year)

        for c in c_qs.select_related('member'):
            entries.append({'date': c.date, 'description': f"Contribution — {c.member.name}", 'inflow': c.amount, 'outflow': Decimal('0.00'), 'type': 'Receipt'})
        for p in p_qs.select_related('member'):
            entries.append({'date': p.date, 'description': f"Loan Repayment — {p.member.name if p.member else 'Borrower'}", 'inflow': p.amount, 'outflow': Decimal('0.00'), 'type': 'Receipt'})
        for pen in pen_qs.select_related('member'):
            entries.append({'date': pen.paid_date or pen.date, 'description': f"Penalty Paid — {pen.member.name}", 'inflow': pen.amount, 'outflow': Decimal('0.00'), 'type': 'Receipt'})
        for rf in rf_qs.select_related('member'):
            entries.append({'date': rf.payment_date, 'description': f"Registration Fee — {rf.member.name}", 'inflow': rf.amount, 'outflow': Decimal('0.00'), 'type': 'Receipt'})
        for oi in other_inc_qs:
            entries.append({'date': oi.date, 'description': f"Other Income — {oi.source}", 'inflow': oi.amount, 'outflow': Decimal('0.00'), 'type': 'Receipt'})

        for exp in exp_qs:
            entries.append({'date': exp.date, 'description': f"Expense — {exp.description}", 'inflow': Decimal('0.00'), 'outflow': exp.amount, 'type': 'Payment'})
        for l in loan_qs.select_related('member'):
            entries.append({'date': l.date_taken, 'description': f"Loan Disbursed — {l.member.name if l.member else l.borrower_name}", 'inflow': Decimal('0.00'), 'outflow': l.loan_amount, 'type': 'Payment'})
        for top in topup_qs.select_related('account'):
            entries.append({'date': top.recorded_on, 'description': f"Cash Banked — {top.account.bank_name} ({top.account.account_number})", 'inflow': Decimal('0.00'), 'outflow': top.topup_amount, 'type': 'Transfer Out'})
        for inv in inv_qs:
            entries.append({'date': inv.start_date, 'description': f"Investment Disbursed — {inv.title}", 'inflow': Decimal('0.00'), 'outflow': inv.principal_amount, 'type': 'Payment'})

        for tr in tr_qs.select_related('from_account', 'to_account'):
            if tr.to_account.account_type == MoneyAccount.TYPE_CASH:
                entries.append({'date': tr.transfer_date, 'description': f"{tr.get_transfer_type_display()} (Ref: {tr.reference})", 'inflow': tr.amount, 'outflow': Decimal('0.00'), 'type': 'Transfer In'})
            else:
                entries.append({'date': tr.transfer_date, 'description': f"{tr.get_transfer_type_display()} (Ref: {tr.reference})", 'inflow': Decimal('0.00'), 'outflow': tr.amount, 'type': 'Transfer Out'})

        try:
            from yearend.models import YearEndWithdrawal
            yw_qs = YearEndWithdrawal.objects.all()
            if year:
                yw_qs = yw_qs.filter(date_withdrawn__year=year)
            for yw in yw_qs.select_related('member'):
                entries.append({'date': yw.date_withdrawn, 'description': f"Year-End Withdrawal — {yw.member.name}", 'inflow': Decimal('0.00'), 'outflow': yw.amount_withdrawn, 'type': 'Payment'})
        except Exception:
            pass

        try:
            from members.models import MemberExit
            me_qs = MemberExit.objects.all()
            if year:
                me_qs = me_qs.filter(exit_date__year=year)
            for me in me_qs.select_related('member'):
                entries.append({'date': me.exit_date, 'description': f"Member Exit Payout — {me.member.name}", 'inflow': Decimal('0.00'), 'outflow': me.net_payout, 'type': 'Payment'})
        except Exception:
            pass

        entries.sort(key=lambda x: x['date'])

        # Calculate running balance
        running = Decimal('0.00')
        for e in entries:
            running += (e['inflow'] - e['outflow'])
            e['running_balance'] = running

        ctx['total_inflows'] = sum((e['inflow'] for e in entries), Decimal('0.00'))
        ctx['total_outflows'] = sum((e['outflow'] for e in entries), Decimal('0.00'))
        ctx['final_balance'] = running
        ctx['entries'] = entries[-200:] # display recent 200 sorted
        return ctx


class BankLedgerReportView(MemberAccessMixin, TemplateView):
    template_name = 'money_movement/reports/bank_ledger.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        bank_id = self.request.GET.get('bank_id', '')
        selected_bank = None
        if bank_id:
            selected_bank = BankAccount.objects.filter(pk=bank_id).first()
        if not selected_bank:
            selected_bank = BankAccount.objects.filter(is_active=True).first()

        ctx['selected_bank'] = selected_bank
        ctx['banks'] = BankAccount.objects.filter(is_active=True)

        if selected_bank:
            ctx['balances'] = selected_bank.balances.order_by('recorded_on', 'created_at')
            ctx['current_balance'] = selected_bank.current_balance
            ctx['total_topups'] = selected_bank.total_topups
        return ctx


class IncomeVsExpensesReportView(MemberAccessMixin, TemplateView):
    template_name = 'money_movement/reports/income_vs_expenses.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        year = self.request.GET.get('year', '')
        today = timezone.localdate()
        ctx['years'] = list(range(today.year - 4, today.year + 1))
        ctx['selected_year'] = year

        pos = get_funds_position()
        ctx['income_breakdown'] = pos['income_breakdown']
        ctx['expense_breakdown'] = pos['expense_breakdown']
        ctx['total_income'] = pos['total_income']
        ctx['total_expenses'] = pos['total_expenses']
        ctx['net_surplus'] = pos['total_income'] - pos['total_expenses']
        return ctx


class InvestmentRegisterReportView(MemberAccessMixin, TemplateView):
    template_name = 'money_movement/reports/investment_register.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        investments = Investment.objects.select_related(
            'investment_type', 'investment_type__category'
        ).prefetch_related('returns', 'withdrawals', 'valuations').order_by('-date_invested')

        total_principal = Decimal('0.00')
        total_current_val = Decimal('0.00')
        total_roi = Decimal('0.00')

        inv_rows = []
        for inv in investments:
            c_val = inv.current_value
            r_val = inv.total_returns_received
            total_principal += inv.initial_amount
            total_current_val += c_val
            total_roi += r_val
            inv_rows.append({
                'investment': inv,
                'principal': inv.initial_amount,
                'current_value': c_val,
                'returns_received': r_val,
                'roi_pct': inv.roi_percentage,
                'net_gain': inv.net_gain_loss,
            })

        ctx['investments'] = inv_rows
        ctx['total_principal'] = total_principal
        ctx['total_current_val'] = total_current_val
        ctx['total_roi'] = total_roi
        ctx['portfolio_total'] = total_current_val + total_roi
        return ctx


class FundsPositionReportView(MemberAccessMixin, TemplateView):
    template_name = 'money_movement/reports/funds_position.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        date_str = self.request.GET.get('date', '')
        today = timezone.localdate()

        as_of_date = today
        if date_str:
            try:
                import datetime
                as_of_date = datetime.date.fromisoformat(date_str)
            except Exception:
                as_of_date = today

        position = get_funds_position(as_of_date=as_of_date)
        ctx.update(position)
        ctx['filter_date'] = as_of_date
        return ctx
