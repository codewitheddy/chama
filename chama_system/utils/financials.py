"""
Shared financial utility for DC Welfare Group.

get_available_fund_balance() is the single source of truth for the
available lending fund balance. All views (dashboard, loan create,
loan rollover) must call this function — never compute inline.

Formula:
    Available_Fund_Balance =
        Total_Income
        − Cash_Lent_Outstanding
        − Total_Year_End_Withdrawals

    Total_Income =
        SUM(Contribution.amount)
        + SUM(Member.registration_fee)
        + SUM(interest_collected per loan)   # min(amount_paid, total_payable - loan_amount)
        + SUM(Penalty.amount where paid=True)

    Cash_Lent_Outstanding =
        SUM(max(loan_amount - amount_paid, 0)) for Loans with status in ('active', 'late')

        Only the actual principal (cash given out) minus repayments is subtracted.
        Interest expected is NOT subtracted — it hasn't left the fund yet.

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

    # --- Income components ---
    total_contributions = (
        Contribution.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    )
    total_reg_fees = (
        Member.objects.aggregate(t=Sum('registration_fee'))['t'] or Decimal('0')
    )
    total_penalties = (
        Penalty.objects.filter(paid=True).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    )

    # Interest collected: per loan = min(amount_paid, total_payable - loan_amount)
    loans_qs = Loan.objects.annotate(
        interest_charged=ExpressionWrapper(
            F('total_payable') - F('loan_amount'),
            output_field=DecimalField(),
        )
    ).only('amount_paid', 'total_payable', 'loan_amount')
    interest_collected = sum(
        min(l.amount_paid, l.interest_charged) for l in loans_qs
    )

    total_income = (
        total_contributions
        + total_reg_fees
        + Decimal(str(interest_collected))
        + total_penalties
    )

    # --- Cash lent outstanding (active + late loans only) ---
    # Only subtract actual principal not yet repaid — NOT interest.
    # For each active/late loan: max(loan_amount - amount_paid, 0)
    active_loans = Loan.objects.filter(
        status__in=['active', 'late']
    ).only('loan_amount', 'amount_paid')

    cash_lent_outstanding = sum(
        max(l.loan_amount - l.amount_paid, Decimal('0'))
        for l in active_loans
    )

    # --- Year-end withdrawals (lazy import to avoid circular deps) ---
    try:
        from yearend.models import YearEndWithdrawal
        total_withdrawals = (
            YearEndWithdrawal.objects.aggregate(t=Sum('amount_withdrawn'))['t']
            or Decimal('0')
        )
    except Exception:
        total_withdrawals = Decimal('0')

    return total_income - cash_lent_outstanding - total_withdrawals
