from decimal import Decimal
from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Q
from django.utils import timezone
import datetime

from contributions.models import Contribution
from loans.models import Loan
from payments.models import Payment
from penalties.models import Penalty
from members.models import Member
from expenses.models import Expense
from other_income.models import OtherIncome
from bank_accounts.models import BankAccount, BankBalance
from investments.models import Investment, InvestmentReturn, InvestmentWithdrawal
from money_movement.models import MoneyAccount, MoneyTransfer


def get_funds_position(as_of_date=None):
    """
    Computes the complete, balanced Funds Position for the Table Banking group.
    Can be evaluated for today or point-in-time for any historical date.

    Invariant:
      TOTAL FUNDS = Cash in Hand + M-Pesa + Bank Balance + Investments (Principal + ROI) + Outstanding Loans
      TOTAL FUNDS == Total Income Received - Total Expenses/Payouts + Initial Opening Balances
    """
    if as_of_date is None:
        as_of_date = timezone.localdate()
    elif isinstance(as_of_date, str):
        as_of_date = datetime.date.fromisoformat(as_of_date)

    # ─────────────────────────────────────────────────────────────
    # 1. CASH IN HAND (Held by Treasurer)
    # ─────────────────────────────────────────────────────────────
    c_in = Contribution.objects.filter(date__lte=as_of_date, payment_type='cash').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    p_in = Payment.objects.filter(date__lte=as_of_date, payment_type='cash').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    pen_in = Penalty.objects.filter(paid=True, paid_date__lte=as_of_date, payment_type='cash').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    
    # Registration fees
    from members.models import RegistrationFeePayment
    reg_in = RegistrationFeePayment.objects.filter(
        payment_date__lte=as_of_date,
        payment_method='cash'
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    other_income_cash = OtherIncome.objects.filter(
        date__lte=as_of_date,
        payment_method=OtherIncome.PAYMENT_CASH
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    
    # Internal transfers into Cash (Bank to Cash, M-Pesa to Cash, Investment return to Cash)
    transfers_cash_in = MoneyTransfer.objects.filter(
        status__in=[MoneyTransfer.STATUS_APPROVED, MoneyTransfer.STATUS_REVERSED],
        transfer_date__lte=as_of_date,
        to_account__account_type=MoneyAccount.TYPE_CASH
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    # Cash Outflows
    transfers_cash_out = MoneyTransfer.objects.filter(
        status__in=[MoneyTransfer.STATUS_APPROVED, MoneyTransfer.STATUS_REVERSED],
        transfer_date__lte=as_of_date,
        from_account__account_type=MoneyAccount.TYPE_CASH
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    # Investments funded directly from group cash
    investments_from_cash = Investment.objects.filter(
        date_invested__lte=as_of_date,
        fund_source='group_funds'
    ).aggregate(s=Sum('initial_amount'))['s'] or Decimal('0.00')

    # Bank deposits made directly before MoneyTransfer module was introduced
    # Only deposits to General Chama accounts reduce general Cash in Hand
    legacy_bank_topups = BankBalance.objects.filter(
        account__fund_type=BankAccount.FUND_TYPE_GENERAL,
        recorded_on__lte=as_of_date,
        transaction_type=BankBalance.TYPE_TOPUP
    ).exclude(notes__contains='Transfer #').aggregate(s=Sum('topup_amount'))['s'] or Decimal('0.00')

    # Loans disbursed from cash (group funds)
    loans_cash_disbursed = Loan.objects.filter(
        date_taken__lte=as_of_date,
        fund_source='group_funds'
    ).aggregate(s=Sum('loan_amount'))['s'] or Decimal('0.00')

    # Expenses paid from cash (group_funds or registration_fees, excluding Welfare)
    expenses_cash = Expense.objects.filter(
        date__lte=as_of_date,
        fund_source__in=['group_funds', 'registration_fees']
    ).exclude(
        category__name='Welfare Expenses'
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    # Year-end withdrawals
    try:
        from yearend.models import YearEndWithdrawal
        yearend_cash = YearEndWithdrawal.objects.filter(
            date_withdrawn__lte=as_of_date
        ).aggregate(s=Sum('amount_withdrawn'))['s'] or Decimal('0.00')
    except Exception:
        yearend_cash = Decimal('0.00')

    # Member exit payouts
    try:
        from members.models import MemberExit
        member_exits_cash = MemberExit.objects.filter(
            exit_date__lte=as_of_date
        ).aggregate(s=Sum('net_payout'))['s'] or Decimal('0.00')
    except Exception:
        member_exits_cash = Decimal('0.00')

    cash_inflows = (c_in + p_in + pen_in + reg_in + other_income_cash + transfers_cash_in)
    cash_outflows = (transfers_cash_out + investments_from_cash + legacy_bank_topups + loans_cash_disbursed + expenses_cash + yearend_cash + member_exits_cash)
    cash_in_hand = cash_inflows - cash_outflows

    # ─────────────────────────────────────────────────────────────
    # 2. M-PESA WALLET
    # ─────────────────────────────────────────────────────────────
    mpesa_c_in = Contribution.objects.filter(date__lte=as_of_date, payment_type='mpesa').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    mpesa_p_in = Payment.objects.filter(date__lte=as_of_date, payment_type='mpesa').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    mpesa_pen_in = Penalty.objects.filter(paid=True, paid_date__lte=as_of_date, payment_type='mpesa').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    mpesa_reg_in = RegistrationFeePayment.objects.filter(
        payment_date__lte=as_of_date,
        payment_method='mpesa'
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    other_income_mpesa = OtherIncome.objects.filter(
        date__lte=as_of_date,
        payment_method=OtherIncome.PAYMENT_MPESA
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    
    transfers_mpesa_in = MoneyTransfer.objects.filter(
        status__in=[MoneyTransfer.STATUS_APPROVED, MoneyTransfer.STATUS_REVERSED],
        transfer_date__lte=as_of_date,
        to_account__account_type=MoneyAccount.TYPE_MPESA
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    transfers_mpesa_out = MoneyTransfer.objects.filter(
        status__in=[MoneyTransfer.STATUS_APPROVED, MoneyTransfer.STATUS_REVERSED],
        transfer_date__lte=as_of_date,
        from_account__account_type=MoneyAccount.TYPE_MPESA
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    mpesa_inflows = (mpesa_c_in + mpesa_p_in + mpesa_pen_in + mpesa_reg_in + other_income_mpesa + transfers_mpesa_in)
    mpesa_outflows = transfers_mpesa_out
    mpesa_wallet = mpesa_inflows - mpesa_outflows

    # ─────────────────────────────────────────────────────────────
    # 3. BANK ACCOUNTS
    # ─────────────────────────────────────────────────────────────
    # General Chama Bank accounts (excludes Welfare and Registration accounts)
    total_bank_balance = Decimal('0.00')
    bank_details = []
    for bank in BankAccount.objects.filter(is_active=True, fund_type=BankAccount.FUND_TYPE_GENERAL):
        latest_bal = bank.balances.filter(recorded_on__lte=as_of_date).order_by('-recorded_on', '-created_at').first()
        bal_amount = latest_bal.balance if latest_bal else Decimal('0.00')
        total_bank_balance += bal_amount
        bank_details.append({
            'account': bank,
            'balance': bal_amount,
            'last_updated': latest_bal.recorded_on if latest_bal else None
        })

    # Dedicated Welfare Bank accounts (tracked separately for Welfare Fund)
    welfare_bank_balance = Decimal('0.00')
    welfare_bank_details = []
    for bank in BankAccount.objects.filter(is_active=True, fund_type=BankAccount.FUND_TYPE_WELFARE):
        latest_bal = bank.balances.filter(recorded_on__lte=as_of_date).order_by('-recorded_on', '-created_at').first()
        bal_amount = latest_bal.balance if latest_bal else Decimal('0.00')
        welfare_bank_balance += bal_amount
        welfare_bank_details.append({
            'account': bank,
            'balance': bal_amount,
            'last_updated': latest_bal.recorded_on if latest_bal else None
        })

    # ─────────────────────────────────────────────────────────────
    # 4. INVESTMENTS (Principal + ROI)
    # ─────────────────────────────────────────────────────────────
    inv_qs = Investment.objects.filter(date_invested__lte=as_of_date)
    investments_principal = Decimal('0.00')
    investments_roi = Decimal('0.00')

    for inv in inv_qs:
        # Principal remains until liquidated
        liquidated_amt = inv.withdrawals.filter(withdrawal_date__lte=as_of_date).aggregate(s=Sum('amount_received'))['s'] or Decimal('0.00')
        active_principal = max(inv.initial_amount - liquidated_amt, Decimal('0.00'))
        investments_principal += active_principal

        returns = inv.returns.filter(return_date__lte=as_of_date).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        investments_roi += returns

    investments_total = investments_principal + investments_roi

    # ─────────────────────────────────────────────────────────────
    # 5. OUTSTANDING LOANS (Receivable)
    # ─────────────────────────────────────────────────────────────
    # Principal outstanding on active or late loans as of date
    loans_taken = Loan.objects.filter(date_taken__lte=as_of_date)
    outstanding_loans = Decimal('0.00')
    outstanding_interest = Decimal('0.00')

    for loan in loans_taken:
        payments_to_date = loan.payment_set.filter(date__lte=as_of_date).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        # Principal balance remaining:
        unpaid_principal = max(loan.loan_amount - payments_to_date, Decimal('0.00'))
        outstanding_loans += unpaid_principal

        # Interest remaining:
        interest_charged = max(loan.total_payable - loan.loan_amount, Decimal('0.00'))
        interest_paid = max(payments_to_date - loan.loan_amount, Decimal('0.00'))
        unpaid_interest = max(interest_charged - interest_paid, Decimal('0.00'))
        outstanding_interest += unpaid_interest

    # ─────────────────────────────────────────────────────────────
    # 6. TOTAL LIQUID & TOTAL FUNDS
    # ─────────────────────────────────────────────────────────────
    total_liquid = cash_in_hand + mpesa_wallet + total_bank_balance
    total_funds = total_liquid + investments_total + outstanding_loans

    # ─────────────────────────────────────────────────────────────
    # 7. TOTAL INCOME RECEIVED (From outside the group)
    # ─────────────────────────────────────────────────────────────
    all_contributions = Contribution.objects.filter(date__lte=as_of_date).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    
    # Interest collected: sum of min(payment, interest_charged) per loan
    total_interest_collected = Decimal('0.00')
    for l in loans_taken:
        total_p = l.payment_set.filter(date__lte=as_of_date).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
        int_charged = max(l.total_payable - l.loan_amount, Decimal('0.00'))
        total_interest_collected += min(total_p, int_charged)

    total_penalties_paid = Penalty.objects.filter(paid=True, paid_date__lte=as_of_date).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    total_registration_fees = RegistrationFeePayment.objects.filter(payment_date__lte=as_of_date).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    
    total_other_income = OtherIncome.objects.filter(date__lte=as_of_date).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    # Initial bank opening balance (capital introduced at start for General Chama)
    bank_opening_balances = sum(b.opening_balance for b in BankAccount.objects.filter(is_active=True, fund_type=BankAccount.FUND_TYPE_GENERAL))

    total_income = (
        all_contributions
        + total_interest_collected
        + total_penalties_paid
        + total_registration_fees
        + total_other_income
        + investments_roi
        + bank_opening_balances
    )

    # ─────────────────────────────────────────────────────────────
    # 8. TOTAL EXPENSES / PAYOUTS
    # ─────────────────────────────────────────────────────────────
    # Only General Chama expenses (exclude Welfare expenses / Welfare bank disbursements)
    total_expenses_recorded = Expense.objects.filter(
        date__lte=as_of_date
    ).exclude(
        fund_source='bank_account',
        fund_source_bank__fund_type=BankAccount.FUND_TYPE_WELFARE
    ).exclude(
        category__name='Welfare Expenses'
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    try:
        from yearend.models import YearEndWithdrawal
        total_yearend_payouts = YearEndWithdrawal.objects.filter(date_withdrawn__lte=as_of_date).aggregate(s=Sum('amount_withdrawn'))['s'] or Decimal('0.00')
    except Exception:
        total_yearend_payouts = Decimal('0.00')

    try:
        from members.models import MemberExit
        total_exit_payouts = MemberExit.objects.filter(exit_date__lte=as_of_date).aggregate(s=Sum('net_payout'))['s'] or Decimal('0.00')
    except Exception:
        total_exit_payouts = Decimal('0.00')

    total_expenses = (
        total_expenses_recorded
        + total_yearend_payouts
        + total_exit_payouts
    )

    # ─────────────────────────────────────────────────────────────
    # 9. INVARIANT CHECK LINE
    # ─────────────────────────────────────────────────────────────
    # Check: Total Income - Total Expenses == TOTAL FUNDS
    expected_funds = total_income - total_expenses
    variance = total_funds - expected_funds
    is_balanced = abs(variance) < Decimal('0.05')

    return {
        'as_of_date': as_of_date,
        'cash_in_hand': cash_in_hand,
        'mpesa_wallet': mpesa_wallet,
        'bank_balance': total_bank_balance,
        'bank_details': bank_details,
        'welfare_bank_balance': welfare_bank_balance,
        'welfare_bank_details': welfare_bank_details,
        'investments_principal': investments_principal,
        'investments_roi': investments_roi,
        'investments_total': investments_total,
        'outstanding_loans': outstanding_loans,
        'outstanding_interest': outstanding_interest,
        'total_liquid': total_liquid,
        'total_funds': total_funds,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'expected_funds': expected_funds,
        'variance': variance,
        'is_balanced': is_balanced,
        # Breakdown of income
        'income_breakdown': {
            'contributions': all_contributions,
            'interest_collected': total_interest_collected,
            'penalties': total_penalties_paid,
            'registration_fees': total_registration_fees,
            'other_income': total_other_income,
            'investment_roi': investments_roi,
            'bank_opening_balances': bank_opening_balances,
        },
        # Breakdown of expenses
        'expense_breakdown': {
            'operating_expenses': total_expenses_recorded,
            'yearend_withdrawals': total_yearend_payouts,
            'member_exits': total_exit_payouts,
        }
    }


def get_account_balances():
    """Returns available balance for each managed MoneyAccount."""
    MoneyAccount.get_or_create_default_cash()
    MoneyAccount.get_or_create_default_mpesa()
    MoneyAccount.get_or_create_default_investments()
    MoneyAccount.sync_bank_accounts()

    position = get_funds_position()
    balances = {}
    for acc in MoneyAccount.objects.filter(is_active=True):
        if acc.account_type == MoneyAccount.TYPE_CASH:
            balances[acc.pk] = position['cash_in_hand']
        elif acc.account_type == MoneyAccount.TYPE_MPESA:
            balances[acc.pk] = position['mpesa_wallet']
        elif acc.account_type == MoneyAccount.TYPE_BANK:
            balances[acc.pk] = acc.bank_account.current_balance if acc.bank_account else Decimal('0.00')
        elif acc.account_type == MoneyAccount.TYPE_INVESTMENT:
            balances[acc.pk] = position['investments_total']
        else:
            balances[acc.pk] = Decimal('0.00')
    return balances
