from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from other_income.models import OtherIncome
from bank_accounts.models import BankAccount, BankBalance
from accounts.models import UserProfile
from money_movement.services import get_funds_position

User = get_user_model()


class OtherIncomeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='treasurer', password='password123')
        self.user.profile.role = 'treasurer'
        self.user.profile.save()
        self.client = Client()
        self.client.login(username='treasurer', password='password123')

        self.bank = BankAccount.objects.create(
            bank_name='KCB Bank',
            account_name='Chama Main Account',
            account_number='1234567890',
            branch='Nairobi'
        )
        # Opening balance
        BankBalance.objects.create(
            account=self.bank,
            balance=Decimal('10000.00'),
            topup_amount=Decimal('10000.00'),
            transaction_type=BankBalance.TYPE_OPENING,
            recorded_on=timezone.localdate(),
        )

    def test_create_bank_transfer_other_income(self):
        """Direct bank transfer should update bank balance and sync bank ledger."""
        initial_bank_bal = self.bank.current_balance
        self.assertEqual(initial_bank_bal, Decimal('10000.00'))

        income = OtherIncome.objects.create(
            source='KCB Fixed Deposit',
            category=OtherIncome.CATEGORY_FIXED_DEPOSIT,
            amount=Decimal('5000.00'),
            date=timezone.localdate(),
            payment_method=OtherIncome.PAYMENT_BANK_TRANSFER,
            bank_account=self.bank,
            reference_number='FD-INT-001',
            recorded_by=self.user,
        )
        income.sync_bank_ledger()

        # Check bank balance increased
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.current_balance, Decimal('15000.00'))

        # Check BankBalance entry exists
        self.assertIsNotNone(income.bank_balance_entry)
        self.assertEqual(income.bank_balance_entry.topup_amount, Decimal('5000.00'))
        self.assertEqual(income.bank_balance_entry.transaction_type, BankBalance.TYPE_TOPUP)

        # Check affected account display
        self.assertIn('KCB Bank', income.affected_account_display)

    def test_create_cash_other_income(self):
        """Cash other income routes to Cash in Hand, not bank."""
        initial_bank_bal = self.bank.current_balance

        income = OtherIncome.objects.create(
            source='Old Chairs Sale',
            category=OtherIncome.CATEGORY_ASSET_SALE,
            amount=Decimal('2500.00'),
            date=timezone.localdate(),
            payment_method=OtherIncome.PAYMENT_CASH,
            recorded_by=self.user,
        )
        income.sync_bank_ledger()

        # Bank balance should NOT change
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.current_balance, initial_bank_bal)
        self.assertIsNone(income.bank_balance_entry)
        self.assertEqual(income.affected_account_display, "Cash in Hand (Treasurer)")

        # Funds position cash in hand should include it
        pos = get_funds_position()
        self.assertGreaterEqual(pos['cash_in_hand'], Decimal('2500.00'))

    def test_create_mpesa_other_income(self):
        """M-Pesa other income routes to M-Pesa wallet."""
        income = OtherIncome.objects.create(
            source='Community Tent Rental',
            category=OtherIncome.CATEGORY_RENTAL,
            amount=Decimal('1500.00'),
            date=timezone.localdate(),
            payment_method=OtherIncome.PAYMENT_MPESA,
            reference_number='QWE123RTY',
            recorded_by=self.user,
        )
        income.sync_bank_ledger()

        self.assertEqual(income.affected_account_display, "M-Pesa Wallet / Till")
        pos = get_funds_position()
        self.assertGreaterEqual(pos['mpesa_wallet'], Decimal('1500.00'))

    def test_reconcile_toggle(self):
        """Treasurer can toggle reconciliation status on other income."""
        income = OtherIncome.objects.create(
            source='Grants Foundation',
            category=OtherIncome.CATEGORY_GRANT,
            amount=Decimal('20000.00'),
            date=timezone.localdate(),
            payment_method=OtherIncome.PAYMENT_BANK_TRANSFER,
            bank_account=self.bank,
            reference_number='GRANT-2026',
            recorded_by=self.user,
        )
        income.sync_bank_ledger()
        self.assertFalse(income.is_reconciled)

        # Toggle to reconciled
        response = self.client.post(reverse('other_income:reconcile_toggle', kwargs={'pk': income.pk}))
        self.assertEqual(response.status_code, 302)

        income.refresh_from_db()
        self.assertTrue(income.is_reconciled)
        self.assertEqual(income.reconciled_by, self.user)
        self.assertIsNotNone(income.reconciled_date)

        # Toggle back to unreconciled
        response = self.client.post(reverse('other_income:reconcile_toggle', kwargs={'pk': income.pk}))
        self.assertEqual(response.status_code, 302)

        income.refresh_from_db()
        self.assertFalse(income.is_reconciled)
        self.assertIsNone(income.reconciled_by)

    def test_delete_other_income_reverses_bank_ledger(self):
        """Deleting an other income removes the bank balance entry."""
        income = OtherIncome.objects.create(
            source='T-Bills Return',
            category=OtherIncome.CATEGORY_TBILL_BOND,
            amount=Decimal('8000.00'),
            date=timezone.localdate(),
            payment_method=OtherIncome.PAYMENT_BANK_TRANSFER,
            bank_account=self.bank,
            reference_number='CBK-TBILL-88',
            recorded_by=self.user,
        )
        income.sync_bank_ledger()
        entry_id = income.bank_balance_entry_id

        # Delete the income
        income.delete()

        # Bank balance entry should be gone
        self.assertFalse(BankBalance.objects.filter(pk=entry_id).exists())

    def test_list_view_renders_200(self):
        """GET /other-income/ renders without NoReverseMatch or template errors."""
        response = self.client.get(reverse('other_income:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Direct Bank Transfers')
        self.assertContains(response, 'Cash Received')

    def test_add_view_renders_200(self):
        """GET /other-income/add/ renders with form."""
        response = self.client.get(reverse('other_income:add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Target Bank Account')

    def test_add_post_direct_bank_transfer(self):
        """POST /other-income/add/ with direct bank transfer creates income and updates bank."""
        response = self.client.post(reverse('other_income:add'), {
            'source': 'Equity Fixed Deposit Interest',
            'category': 'fixed_deposit',
            'amount': '3500.00',
            'date': timezone.localdate().isoformat(),
            'payment_method': 'bank_transfer',
            'bank_account': self.bank.pk,
            'reference_number': 'EQ-INT-2026',
            'description': 'Quarterly interest deposit',
        })
        self.assertEqual(response.status_code, 302)
        income = OtherIncome.objects.filter(source='Equity Fixed Deposit Interest').first()
        self.assertIsNotNone(income)
        self.assertEqual(income.amount, Decimal('3500.00'))
        self.assertIsNotNone(income.bank_balance_entry)
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.current_balance, Decimal('13500.00'))

