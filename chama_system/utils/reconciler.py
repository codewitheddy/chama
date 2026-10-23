"""
System Compatibility & Database Reconciler Layer.
=================================================
Ensures that whenever an older backup database is restored or the application
starts up with an existing database from a previous version, the database is
automatically upgraded to the latest version and all newest features remain
active, configured, and segregated without losing any member or financial data.
"""

import logging
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.core.management import call_command

logger = logging.getLogger(__name__)


def run_database_migrations():
    """Apply any pending migrations to the active database."""
    try:
        call_command('migrate', interactive=False, verbosity=0)
        return True
    except Exception as exc:
        logger.warning(f"Reconciler migration notice: {exc}")
        return False


def reconcile_bank_accounts():
    """
    Ensure the dedicated Welfare Bank Account is properly segregated.
    When restoring legacy databases where fund_type was not set, automatically
    identifies the welfare/current account and marks it as fund_type='welfare'.
    """
    try:
        from bank_accounts.models import BankAccount
        from money_movement.models import MoneyAccount

        # Check if an account already has fund_type='welfare'
        if BankAccount.objects.filter(fund_type=BankAccount.FUND_TYPE_WELFARE).exists():
            return None

        # Look for candidates
        candidate = (
            BankAccount.objects.filter(bank_name__icontains='welfare').first() or
            BankAccount.objects.filter(account_name__icontains='welfare').first() or
            BankAccount.objects.filter(branch__icontains='welfare').first() or
            BankAccount.objects.filter(bank_name__icontains='current').first() or
            BankAccount.objects.filter(account_name__icontains='current').first() or
            (BankAccount.objects.count() > 1 and BankAccount.objects.order_by('pk')[1])
        )

        if candidate:
            candidate.fund_type = BankAccount.FUND_TYPE_WELFARE
            candidate.save(update_fields=['fund_type'])
            # Deactivate commingled money movements for the segregated welfare bank
            MoneyAccount.objects.filter(
                account_type='bank',
                name__icontains=candidate.bank_name
            ).update(is_active=False)
            logger.info(f"Reconciler: Auto-designated Welfare Bank Account: {candidate.bank_name} (ID={candidate.pk})")
            return candidate.bank_name

        return None
    except Exception as exc:
        logger.warning(f"Reconciler bank account notice: {exc}")
        return None


def reconcile_system_settings():
    """
    Ensure SystemSetting holds current version metadata and default configs.
    """
    try:
        from loans.models import SystemSetting
        app_ver = getattr(settings, 'APP_VERSION', '1.1.0')
        SystemSetting.set('app_version', app_ver, label='Application Version', help_text='Current active version of Finance Wise TBM')
        SystemSetting.set('last_upgrade_date', timezone.now().strftime('%Y-%m-%d %H:%M:%S'), label='Last Database Upgrade')

        # Ensure default currency and interest rate exist if missing
        if not SystemSetting.objects.filter(key='group_currency').exists():
            SystemSetting.set('group_currency', 'KES', label='Currency')
        if not SystemSetting.objects.filter(key='default_interest_rate').exists():
            SystemSetting.set('default_interest_rate', '10.00', label='Default Interest Rate (%)')
        if not SystemSetting.objects.filter(key='grace_period_days').exists():
            SystemSetting.set('grace_period_days', '0', label='Grace Period (Days)')
        return True
    except Exception as exc:
        logger.warning(f"Reconciler system settings notice: {exc}")
        return False


def reconcile_loan_products():
    """
    Ensure built-in loan products (including Emergency Loan) exist.
    """
    try:
        from loans.models import LoanProduct

        # 1. Emergency Loan
        if not LoanProduct.objects.filter(is_emergency=True).exists():
            LoanProduct.objects.get_or_create(
                name='Emergency Loan',
                defaults={
                    'description': (
                        'Interest-free emergency loan for members in urgent need. '
                        'Repayment period is agreed upon at the time of issue — '
                        'typically 1 month. No interest is charged.'
                    ),
                    'interest_type': 'emergency',
                    'interest_frequency': 'monthly',
                    'interest_rate': Decimal('0.00'),
                    'duration_months': 1,
                    'min_amount': Decimal('0.00'),
                    'max_amount': Decimal('0.00'),
                    'is_active': True,
                    'is_emergency': True,
                }
            )

        # 2. Ensure at least one standard loan product exists if table is empty
        if LoanProduct.objects.count() == 1 and LoanProduct.objects.filter(is_emergency=True).exists():
            LoanProduct.objects.get_or_create(
                name='Standard Normal Loan',
                defaults={
                    'description': 'Standard chama personal loan at 10% monthly interest.',
                    'interest_type': 'flat',
                    'interest_frequency': 'monthly',
                    'interest_rate': Decimal('10.00'),
                    'duration_months': 3,
                    'min_amount': Decimal('0.00'),
                    'max_amount': Decimal('0.00'),
                    'is_active': True,
                    'is_emergency': False,
                }
            )
        return True
    except Exception as exc:
        logger.warning(f"Reconciler loan products notice: {exc}")
        return False


def reconcile_investment_categories():
    """
    Ensure standard investment categories exist if table is empty.
    """
    try:
        from investments.models import InvestmentCategory
        if InvestmentCategory.objects.count() == 0:
            default_categories = [
                ('Fixed Deposits & Treasury', 'Bank fixed deposits, treasury bills, and bonds', 'bi-bank', '#2563eb', 1),
                ('Real Estate & Land', 'Plots, buildings, and commercial real estate', 'bi-building', '#16a34a', 2),
                ('Equities & Shares', 'Stock market shares and cooperative equity investments', 'bi-graph-up-arrow', '#7c3aed', 3),
                ('Agribusiness & Ventures', 'Agricultural projects, livestock, and trading ventures', 'bi-tree', '#d97706', 4),
            ]
            for name, desc, icon, color, order in default_categories:
                InvestmentCategory.objects.get_or_create(
                    name=name,
                    defaults={
                        'description': desc,
                        'icon': icon,
                        'color_code': color,
                        'display_order': order,
                        'is_active': True,
                    }
                )
        return True
    except Exception as exc:
        logger.warning(f"Reconciler investment categories notice: {exc}")
        return False


def reconcile_all(caller: str = 'system') -> dict:
    """
    Main entry point: executes the full database upgrade & compatibility pipeline.
    Safe to run repeatedly; idempotent across all apps.
    """
    report = {
        'caller': caller,
        'app_version': getattr(settings, 'APP_VERSION', '1.1.0'),
        'timestamp': timezone.now().isoformat(),
        'migrations_applied': False,
        'welfare_bank': None,
        'system_settings': False,
        'loan_products': False,
        'investment_categories': False,
    }

    report['migrations_applied'] = run_database_migrations()
    report['welfare_bank'] = reconcile_bank_accounts()
    report['system_settings'] = reconcile_system_settings()
    report['loan_products'] = reconcile_loan_products()
    report['investment_categories'] = reconcile_investment_categories()

    logger.info(f"Database reconciliation completed (caller: {caller}): {report}")
    return report
