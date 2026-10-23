"""
Management command: reset_group_data

Wipes all operational and financial test/demo data (members, contributions,
loans, welfare records, meetings, penalties, expenses, investments, other income,
money movement, audit logs, recycle bin, uploaded media) while keeping the database
schema, administrative user accounts, rate rules, and group settings intact.

Usage:
    python manage.py reset_group_data
    python manage.py reset_group_data --yes   # skip confirmation prompt
"""

import os
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings


class Command(BaseCommand):
    help = "Delete all members, financial transactions, and operational logs for a fresh group start."

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            help='Skip the confirmation prompt.',
        )

    def handle(self, *args, **options):
        if not options['yes']:
            confirm = input(
                "\n[WARNING]  This will permanently delete ALL members, contributions, "
                "loans, meetings, expenses, investments, and audit logs.\nType 'yes' to continue: "
            )
            if confirm.strip().lower() != 'yes':
                self.stdout.write(self.style.WARNING("Aborted. No data was deleted."))
                return

        with transaction.atomic():
            # Import here to avoid circular import issues at module load time
            from django.contrib.admin.models import LogEntry
            from django.contrib.sessions.models import Session
            from audit.models import AuditLog
            from recycle_bin.models import DeletedRecord
            from yearend.models import YearEndMemberStatus, MemberInterestShare, YearEndWithdrawal
            from penalties.models import Penalty
            from meetings.models import MeetingPenalty, MeetingAttendance, Meeting
            from payments.models import Payment
            from loans.models import (
                RepaymentSchedule, LoanRestructure, LoanRollover, Collateral,
                LoanGuarantor, LoanApplication, Loan, NonMemberApplicant
            )
            from welfare.models import (
                WelfareExternalSupport, WelfareSupportContribution, WelfareDisbursement,
                WelfareEvent, WelfareContribution
            )
            from contributions.models import Contribution
            from expenses.models import Expense
            from investments.models import (
                InvestmentWithdrawal, InvestmentValuation, InvestmentReturn, Investment
            )
            from other_income.models import OtherIncome
            from money_movement.models import (
                MoneyTransfer, CashReconciliation, BankReconciliation, MoneyAccount
            )
            from bank_accounts.models import BankAccount, BankBalance
            from backup.models import BackupLog
            from members.models import RegistrationFeePayment, MemberExit, Member

            steps = [
                ("Audit logs",                     AuditLog),
                ("Recycle bin records",            DeletedRecord),
                ("Year-end member statuses",       YearEndMemberStatus),
                ("Year-end interest shares",       MemberInterestShare),
                ("Year-end withdrawals",           YearEndWithdrawal),
                ("Penalties",                      Penalty),
                ("Meeting penalties",              MeetingPenalty),
                ("Meeting attendances",            MeetingAttendance),
                ("Meetings",                       Meeting),
                ("Payments",                       Payment),
                ("Loan repayment schedules",       RepaymentSchedule),
                ("Loan restructures",              LoanRestructure),
                ("Loan rollovers",                 LoanRollover),
                ("Loan collaterals",               Collateral),
                ("Loan guarantors",                LoanGuarantor),
                ("Loan applications",              LoanApplication),
                ("Loans",                          Loan),
                ("Non-member applicants",          NonMemberApplicant),
                ("Welfare external supports",      WelfareExternalSupport),
                ("Welfare support contributions",  WelfareSupportContribution),
                ("Welfare disbursements",          WelfareDisbursement),
                ("Welfare events",                 WelfareEvent),
                ("Welfare contributions",          WelfareContribution),
                ("Contributions",                  Contribution),
                ("Expenses",                       Expense),
                ("Investment withdrawals",         InvestmentWithdrawal),
                ("Investment valuations",          InvestmentValuation),
                ("Investment returns",             InvestmentReturn),
                ("Investments",                    Investment),
                ("Other income",                   OtherIncome),
                ("Money transfers",                MoneyTransfer),
                ("Cash reconciliations",           CashReconciliation),
                ("Bank reconciliations",           BankReconciliation),
                ("Bank balances",                  BankBalance),
                ("Bank accounts",                  BankAccount),
                ("Registration fee payments",      RegistrationFeePayment),
                ("Member exits",                   MemberExit),
                ("Members",                        Member),
                ("Sessions",                       Session),
                ("Backup logs",                    BackupLog),
                ("Admin log entries",              LogEntry),
            ]

            totals = {}
            for label, Model in steps:
                count, _ = Model.objects.all().delete()
                totals[label] = count
                if count > 0:
                    self.stdout.write(f"  Deleted {count:>5} {label}")

            # Reset Money Accounts
            deleted_bank_accounts, _ = MoneyAccount.objects.filter(account_type=MoneyAccount.TYPE_BANK).delete()
            if deleted_bank_accounts > 0:
                self.stdout.write(f"  Deleted {deleted_bank_accounts:>5} bank-linked Money Accounts")
            MoneyAccount.objects.all().update(opening_balance=Decimal('0.00'))
            self.stdout.write("  Reset Money Accounts opening balances to 0.00")

            # Clear any audit logs generated by signal handlers during deletion
            AuditLog.objects.all().delete()

        # Clean media directories (keep branding)
        media_root = getattr(settings, 'MEDIA_ROOT', None)
        if media_root and os.path.exists(media_root):
            cleaned_media_count = 0
            for item in os.listdir(media_root):
                if item == 'branding':
                    continue
                item_path = os.path.join(media_root, item)
                if os.path.isdir(item_path):
                    for root, dirs, files in os.walk(item_path):
                        for file in files:
                            try:
                                os.remove(os.path.join(root, file))
                                cleaned_media_count += 1
                            except Exception:
                                pass
            if cleaned_media_count > 0:
                self.stdout.write(f"  Cleaned {cleaned_media_count} uploaded media files (branding preserved)")

        self.stdout.write(self.style.SUCCESS("\n[SUCCESS] Group data reset complete. Schema, users, and settings are untouched."))
