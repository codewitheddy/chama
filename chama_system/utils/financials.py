"""
Shared financial utility for 'Finance Wise TBM'.

get_available_fund_balance() is the single source of truth for the
available lending fund balance.

Formula:
    Available_Fund_Balance =
        Total_Income - Cash_Lent_Outstanding - Total_Year_End_Withdrawals

    Total_Income =
        SUM(Contribution.amount)
        + SUM(interest_collected per loan)
        + SUM(Penalty.amount where paid=True)
        + SUM(OtherIncome.amount)

    NOTE: Registration fees are a SEPARATE fund (Registration Fee Fund)
    and are NOT included in Total_Income or year-end calculations.

    Cash_Lent_Outstanding =
        SUM(max(loan_amount - amount_paid, 0)) for active/late loans

    Total_Year_End_Withdrawals =
        SUM(YearEndWithdrawal.amount_withdrawn)
"""
from decimal import Decimal
from django.db.models import Sum, F, ExpressionWrapper, DecimalField


def get_available_fund_balance() -> Decimal:
    """Return the current available fund balance as a Decimal."""
    from contributions.models import Contribution
    from members.models import Member
    from loans.models import Loan
    from penalties.models import Penalty

    total_contributions = (
        Contribution.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    )
    # Registration fees are a SEPARATE fund — not counted in group lending balance
    total_penalties = (
        Penalty.objects.filter(paid=True).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    )

    loans_qs = Loan.objects.annotate(
        interest_charged=ExpressionWrapper(
            F('total_payable') - F('loan_amount'),
            output_field=DecimalField(),
        )
    ).only('amount_paid', 'total_payable', 'loan_amount')
    interest_collected = sum(
        min(l.amount_paid, l.interest_charged) for l in loans_qs
    )

    # Other income (external interest, investments, etc.)
    try:
        from other_income.models import OtherIncome
        total_other_income = (
            OtherIncome.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        )
    except Exception:
        total_other_income = Decimal('0')

    total_income = (
        total_contributions
        + Decimal(str(interest_collected))
        + total_penalties
        + total_other_income
    )

    active_loans = Loan.objects.filter(
        status__in=['active', 'late']
    ).only('loan_amount', 'amount_paid')
    cash_lent_outstanding = sum(
        max(l.loan_amount - l.amount_paid, Decimal('0'))
        for l in active_loans
    )

    try:
        from yearend.models import YearEndWithdrawal
        total_withdrawals = (
            YearEndWithdrawal.objects.aggregate(t=Sum('amount_withdrawn'))['t']
            or Decimal('0')
        )
    except Exception:
        total_withdrawals = Decimal('0')

    # Group fund expenses reduce the available balance
    try:
        from expenses.models import Expense
        total_group_expenses = (
            Expense.objects.filter(fund_source='group_funds')
            .aggregate(t=Sum('amount'))['t'] or Decimal('0')
        )
    except Exception:
        total_group_expenses = Decimal('0')

    # Member exit payouts reduce the available balance
    try:
        from members.models import MemberExit
        total_member_exits = (
            MemberExit.objects.aggregate(t=Sum('net_payout'))['t'] or Decimal('0')
        )
    except Exception:
        total_member_exits = Decimal('0')

    return total_income - cash_lent_outstanding - total_withdrawals - total_group_expenses - total_member_exits


def get_total_bank_balance(fund_type='general') -> Decimal:
    """
    Return the sum of current balances across active bank accounts.
    Defaults to 'general' (Chama Lending pool) so Welfare accounts are not commingled.
    Pass None to get the absolute sum of all bank accounts regardless of fund.
    """
    try:
        from bank_accounts.models import BankAccount
        qs = BankAccount.objects.filter(is_active=True)
        if fund_type:
            qs = qs.filter(fund_type=fund_type)
        accounts = qs.prefetch_related('balances')
        return sum(a.current_balance for a in accounts)
    except Exception:
        return Decimal('0')


def get_welfare_bank_balance() -> Decimal:
    """Return the total balance held in dedicated Welfare bank accounts."""
    return get_total_bank_balance(fund_type='welfare')


def get_registration_fee_balance() -> Decimal:
    """
    Return the available Registration Fee Fund balance.

    Formula:
        Balance = SUM(Member.registration_fee_paid for all active members)
                - SUM(Expense.amount where fund_source='registration_fees')

    Registration fees are a SEPARATE fund — not part of the group lending pool.
    """
    from members.models import Member

    total_in = (
        Member.objects.aggregate(t=Sum('registration_fee_paid'))['t'] or Decimal('0')
    )

    try:
        from expenses.models import Expense
        total_out = (
            Expense.objects.filter(fund_source='registration_fees')
            .aggregate(t=Sum('amount'))['t'] or Decimal('0')
        )
    except Exception:
        total_out = Decimal('0')

    return max(total_in - total_out, Decimal('0'))
