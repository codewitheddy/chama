from decimal import Decimal
import datetime
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError

from members.models import Member, RegistrationFeePayment
from contributions.models import Contribution
from loans.models import Loan
from payments.models import Payment
from penalties.models import Penalty
from expenses.models import Expense, ExpenseCategory
from bank_accounts.models import BankAccount, BankBalance
from investments.models import Investment, InvestmentType, InvestmentCategory, InvestmentReturn
from money_movement.models import MoneyAccount, MoneyTransfer, CashReconciliation, BankReconciliation
from money_movement.services import get_funds_position, get_account_balances
from welfare.models import WelfareEvent, WelfareSupportContribution


class MoneyMovementModelAndTransferTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="treasurer_admin", password="password123")
        self.member = Member.objects.create(name="Grace Wanjiku", phone="+254712345678")

        # Initial bank account
        self.bank = BankAccount.objects.create(
            bank_name="Equity Bank",
            account_name="Chama Main",
            account_number="0123456789",
            branch="Kilimani"
        )
        BankBalance.objects.create(
            account=self.bank,
            balance=Decimal('10000.00'),
            topup_amount=Decimal('10000.00'),
            transaction_type=BankBalance.TYPE_OPENING,
            recorded_on=timezone.localdate(),
            recorded_by=self.admin
        )

        # Setup accounts
        self.cash_acc = MoneyAccount.get_or_create_default_cash()
        self.mpesa_acc = MoneyAccount.get_or_create_default_mpesa()
        MoneyAccount.sync_bank_accounts()
        self.bank_acc = MoneyAccount.objects.get(bank_account=self.bank)

        # Record contributions: 50,000 cash, 10,000 mpesa
        Contribution.objects.create(
            member=self.member,
            amount=Decimal('50000.00'),
            date=timezone.localdate(),
            month=timezone.localdate().month,
            year=timezone.localdate().year,
            payment_type='cash'
        )
        Contribution.objects.create(
            member=self.member,
            amount=Decimal('10000.00'),
            date=timezone.localdate(),
            month=timezone.localdate().month,
            year=timezone.localdate().year,
            payment_type='mpesa',
            mpesa_code='QWE123RTY'
        )

    def test_funds_position_invariant_balanced(self):
        """Verify that Total Funds equals Net Income (Difference is 0.00)."""
        pos = get_funds_position()
        self.assertEqual(pos['cash_in_hand'], Decimal('50000.00'))
        self.assertEqual(pos['mpesa_wallet'], Decimal('10000.00'))
        self.assertEqual(pos['bank_balance'], Decimal('10000.00'))
        self.assertEqual(pos['total_liquid'], Decimal('70000.00'))
        self.assertEqual(pos['total_funds'], Decimal('70000.00'))
        self.assertEqual(pos['expected_funds'], Decimal('70000.00'))
        self.assertEqual(pos['variance'], Decimal('0.00'))
        self.assertTrue(pos['is_balanced'])

    def test_transfer_cash_to_bank_preserves_total_funds(self):
        """Moving 15,000 from Cash in Hand to Bank decreases Cash, increases Bank, and leaves Total Funds unchanged."""
        transfer = MoneyTransfer.objects.create(
            from_account=self.cash_acc,
            to_account=self.bank_acc,
            amount=Decimal('15000.00'),
            transfer_date=timezone.localdate(),
            transfer_type=MoneyTransfer.TYPE_CASH_TO_BANK,
            reference='DEP-99001',
            deposited_by='Treasurer Grace',
            status=MoneyTransfer.STATUS_APPROVED,
            recorded_by=self.admin,
            approved_by=self.admin
        )
        transfer._sync_with_bank_ledger()

        pos = get_funds_position()
        self.assertEqual(pos['cash_in_hand'], Decimal('35000.00'))
        self.assertEqual(pos['bank_balance'], Decimal('25000.00'))
        self.assertEqual(pos['total_funds'], Decimal('70000.00'))
        self.assertEqual(pos['variance'], Decimal('0.00'))
        self.assertTrue(pos['is_balanced'])

    def test_transfer_same_account_validation_error(self):
        """Clean method blocks transferring funds from an account to itself."""
        transfer = MoneyTransfer(
            from_account=self.cash_acc,
            to_account=self.cash_acc,
            amount=Decimal('1000.00'),
            recorded_by=self.admin
        )
        with self.assertRaises(ValidationError):
            transfer.clean()

    def test_transfer_immutability_and_reversal(self):
        """Completed transfers cannot be modified; corrections must be done via reversal."""
        transfer = MoneyTransfer.objects.create(
            from_account=self.mpesa_acc,
            to_account=self.cash_acc,
            amount=Decimal('5000.00'),
            transfer_date=timezone.localdate(),
            transfer_type=MoneyTransfer.TYPE_MPESA_TO_CASH,
            reference='MPESA-WITHDRAW-1',
            status=MoneyTransfer.STATUS_APPROVED,
            recorded_by=self.admin,
            approved_by=self.admin
        )

        # Attempting to change amount directly on completed transfer raises ValidationError
        transfer.amount = Decimal('8000.00')
        with self.assertRaises(ValidationError):
            transfer.save()

        # Reversal works and posts opposite entry
        transfer.amount = Decimal('5000.00') # reset back
        reversal = transfer.create_reversal(self.admin, "Withdrew cash by mistake")

        transfer.refresh_from_db()
        self.assertEqual(transfer.status, MoneyTransfer.STATUS_REVERSED)
        self.assertEqual(reversal.from_account, self.cash_acc)
        self.assertEqual(reversal.to_account, self.mpesa_acc)
        self.assertEqual(reversal.amount, Decimal('5000.00'))
        self.assertTrue(reversal.is_reversal)
        self.assertEqual(reversal.reversal_of, transfer)

        # Funds position is restored back to original
        pos = get_funds_position()
        self.assertEqual(pos['cash_in_hand'], Decimal('50000.00'))
        self.assertEqual(pos['mpesa_wallet'], Decimal('10000.00'))
        self.assertTrue(pos['is_balanced'])

    def test_dual_approval_workflow(self):
        """Pending transfer requires second officer approval before posting."""
        officer2 = User.objects.create_user(username="secretary_user", password="password123")
        officer2.profile.role = 'treasurer'
        officer2.profile.save()

        transfer = MoneyTransfer.objects.create(
            from_account=self.cash_acc,
            to_account=self.bank_acc,
            amount=Decimal('20000.00'),
            transfer_date=timezone.localdate(),
            transfer_type=MoneyTransfer.TYPE_CASH_TO_BANK,
            reference='SLIP-PENDING-01',
            status=MoneyTransfer.STATUS_PENDING,
            recorded_by=self.admin
        )

        # In pending state, cash is not yet deducted
        pos = get_funds_position()
        self.assertEqual(pos['cash_in_hand'], Decimal('50000.00'))

        # Approve by officer2
        transfer.approve(officer2)
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, MoneyTransfer.STATUS_APPROVED)
        self.assertEqual(transfer.approved_by, officer2)

        # Now cash is deducted and bank updated
        pos = get_funds_position()
        self.assertEqual(pos['cash_in_hand'], Decimal('30000.00'))
        self.assertEqual(pos['bank_balance'], Decimal('30000.00'))
        self.assertTrue(pos['is_balanced'])


class MoneyMovementReconciliationAndReportsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin_recon", password="password123")
        self.client = Client()
        self.client.force_login(self.admin)

        self.member = Member.objects.create(name="David Ochieng", phone="+254722000111")
        self.cash_acc = MoneyAccount.get_or_create_default_cash()
        self.mpesa_acc = MoneyAccount.get_or_create_default_mpesa()

        # Seed 10,000 cash contribution
        Contribution.objects.create(
            member=self.member,
            amount=Decimal('10000.00'),
            date=timezone.localdate(),
            month=timezone.localdate().month,
            year=timezone.localdate().year,
            payment_type='cash'
        )

    def test_cash_reconciliation_exact_and_variance(self):
        """Cash count form correctly flags exact match or variance."""
        res = self.client.get('/money-movement/reconciliation/cash/')
        self.assertEqual(res.status_code, 200)

        # Exact count: 10 x KES 1000 notes = KES 10,000.00
        post_data = {
            'reconciliation_date': timezone.localdate().isoformat(),
            'notes_1000': 10,
            'notes_500': 0,
            'notes_200': 0,
            'notes_100': 0,
            'notes_50': 0,
            'coins_amount': '0.00',
            'notes': 'All notes present and verified.',
        }
        res_post = self.client.post('/money-movement/reconciliation/cash/', data=post_data)
        self.assertEqual(res_post.status_code, 302)

        recon = CashReconciliation.objects.first()
        self.assertIsNotNone(recon)
        self.assertEqual(recon.actual_cash, Decimal('10000.00'))
        self.assertEqual(recon.variance, Decimal('0.00'))
        self.assertEqual(recon.status, CashReconciliation.STATUS_BALANCED)

    def test_bank_reconciliation_view(self):
        """Bank reconciliation checks statement ending balance vs system ledger."""
        bank = BankAccount.objects.create(bank_name="KCB", account_name="Chama KCB")
        BankBalance.objects.create(
            account=bank,
            balance=Decimal('25000.00'),
            topup_amount=Decimal('25000.00'),
            transaction_type=BankBalance.TYPE_OPENING,
            recorded_on=timezone.localdate(),
            recorded_by=self.admin
        )

        res = self.client.get(f'/money-movement/reconciliation/bank/?bank_id={bank.pk}')
        self.assertEqual(res.status_code, 200)

        # Post matching statement balance
        post_data = {
            'bank_account': bank.pk,
            'statement_date': timezone.localdate().isoformat(),
            'statement_balance': '25000.00',
            'unreconciled_items_notes': '',
            'notes': 'Statement checked and matches ledger perfectly.',
        }
        res_post = self.client.post(f'/money-movement/reconciliation/bank/?bank_id={bank.pk}', data=post_data)
        self.assertEqual(res_post.status_code, 302)

        recon = BankReconciliation.objects.first()
        self.assertIsNotNone(recon)
        self.assertEqual(recon.variance, Decimal('0.00'))
        self.assertEqual(recon.status, BankReconciliation.STATUS_RECONCILED)

    def test_dashboard_and_reports_render_200(self):
        """All money movement dashboard and report views render successfully with code 200."""
        urls = [
            '/money-movement/',
            '/money-movement/transfers/',
            '/money-movement/transfers/add/',
            '/money-movement/reports/meeting-summary/',
            '/money-movement/reports/cash-book/',
            '/money-movement/reports/bank-ledger/',
            '/money-movement/reports/income-vs-expenses/',
            '/money-movement/reports/investments/',
            '/money-movement/reports/funds-position/',
        ]
        for url in urls:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200, f"URL {url} failed with status {res.status_code}")

    def test_welfare_funds_excluded_from_funds_position(self):
        """Welfare dues, disbursements, and event support are excluded from core Funds Position invariant."""
        event = WelfareEvent.objects.create(
            beneficiary=self.member,
            description="Hospital admission",
            date_opened=timezone.localdate(),
            status='open'
        )
        # Member contributes KES 5,000 cash towards welfare emergency case
        WelfareSupportContribution.objects.create(
            event=event,
            contributor=self.member,
            amount=Decimal('5000.00'),
            date=timezone.localdate(),
            payment_type='cash'
        )

        # Core Chama funds position remains strictly 10,000.00 cash (welfare is excluded)
        pos = get_funds_position()
        self.assertEqual(pos['cash_in_hand'], Decimal('10000.00'))
        self.assertTrue(pos['is_balanced'])
        self.assertEqual(pos['variance'], Decimal('0.00'))
