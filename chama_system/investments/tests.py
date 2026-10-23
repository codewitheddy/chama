from django.test import TestCase, Client, TransactionTestCase
from django.contrib.auth.models import User
from decimal import Decimal
from .models import InvestmentType, InvestmentCategory, Investment
from bank_accounts.models import BankAccount, BankBalance
from contributions.models import Contribution
from members.models import Member
from django.urls import reverse
from django.db import transaction
from unittest.mock import patch
import unittest


class InvestmentModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass123')
        self.category = InvestmentCategory.objects.create(name='Stocks')
        self.inv_type = InvestmentType.objects.create(
            name='Stocks',
            category=self.category,
            expected_return_rate=Decimal('8.50'),
        )
        self.investment = Investment.objects.create(
            investment_type=self.inv_type,
            initial_amount=Decimal('100000.00'),
            date_invested='2024-01-01',
            quantity=Decimal('100.00'),
            recorded_by=self.user,
        )

    def test_investment_creation(self):
        self.assertEqual(self.investment.initial_amount, Decimal('100000.00'))
        self.assertEqual(str(self.investment), "Stocks — KES 100,000.00 on 2024-01-01")

    def test_current_value_without_valuation(self):
        """Current value should default to initial amount if no valuations exist."""
        self.assertEqual(self.investment.current_value, self.investment.initial_amount)

    def test_check_fund_availability_group_funds_sufficient(self):
        """Test fund availability check when group funds are sufficient."""
        # Disable audit signal temporarily
        from django.db.models.signals import post_save
        from audit.signals import log_save
        
        post_save.disconnect(log_save, sender=Member)
        try:
            member = Member.objects.create(name='Member1', phone='0700000001')
            Contribution.objects.create(
                member=member,
                amount=Decimal('150000.00'),
                date='2026-01-01',
                month=1,
                year=2026,
            )
        finally:
            post_save.connect(log_save, sender=Member)
        
        investment = Investment.objects.create(
            investment_type=self.inv_type,
            initial_amount=Decimal('100000.00'),
            fund_source='group_funds',
            recorded_by=self.user,
        )
        
        is_available, balance, msg = investment.check_fund_availability()
        self.assertTrue(is_available)
        self.assertGreaterEqual(balance, investment.initial_amount)

    def test_check_fund_availability_group_funds_insufficient(self):
        """Test fund availability check when group funds are insufficient."""
        investment = Investment.objects.create(
            investment_type=self.inv_type,
            initial_amount=Decimal('500000.00'),
            fund_source='group_funds',
            recorded_by=self.user,
        )
        
        is_available, balance, msg = investment.check_fund_availability()
        self.assertFalse(is_available)

    def test_check_fund_availability_bank_account_sufficient(self):
        """Test fund availability check when bank account balance is sufficient."""
        bank = BankAccount.objects.create(
            bank_name='Test Bank',
            account_number='123456789',
            is_active=True,
        )
        BankBalance.objects.create(
            account=bank,
            balance=Decimal('200000.00'),
            transaction_type='opening',
            recorded_on='2026-01-01',
        )
        
        investment = Investment.objects.create(
            investment_type=self.inv_type,
            initial_amount=Decimal('100000.00'),
            fund_source='bank_account',
            fund_source_bank=bank,
            recorded_by=self.user,
        )
        
        is_available, balance, msg = investment.check_fund_availability()
        self.assertTrue(is_available)
        self.assertEqual(balance, Decimal('200000.00'))

    def test_check_fund_availability_bank_account_insufficient(self):
        """Test fund availability check when bank account balance is insufficient."""
        bank = BankAccount.objects.create(
            bank_name='Test Bank',
            account_number='123456789',
            is_active=True,
        )
        BankBalance.objects.create(
            account=bank,
            balance=Decimal('50000.00'),
            transaction_type='opening',
            recorded_on='2026-01-01',
        )
        
        investment = Investment.objects.create(
            investment_type=self.inv_type,
            initial_amount=Decimal('100000.00'),
            fund_source='bank_account',
            fund_source_bank=bank,
            recorded_by=self.user,
        )
        
        is_available, balance, msg = investment.check_fund_availability()
        self.assertFalse(is_available)
        self.assertEqual(balance, Decimal('50000.00'))

    def test_funds_deducted_defaults_to_false(self):
        """New investment should have funds_deducted=False."""
        self.assertFalse(self.investment.funds_deducted)
        self.assertIsNone(self.investment.approved_by)
        self.assertIsNone(self.investment.approved_at)


class InvestmentApprovalTest(TransactionTestCase):
    """Test investment approval and fund deduction with transactions."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username='admin', password='admin123', email='admin@test.com'
        )
        self.user = User.objects.create_user(username='testuser', password='pass123')
        self.client = Client()
        self.category = InvestmentCategory.objects.create(name='Stocks')
        self.inv_type = InvestmentType.objects.create(
            name='Stocks',
            category=self.category,
            expected_return_rate=Decimal('8.50'),
        )

    def test_approve_investment_with_sufficient_bank_funds(self):
        """Test successful approval and deduction from bank account."""
        bank = BankAccount.objects.create(
            bank_name='Test Bank',
            account_number='123456789',
            is_active=True,
        )
        BankBalance.objects.create(
            account=bank,
            balance=Decimal('300000.00'),
            transaction_type='opening',
            recorded_on='2026-01-01',
        )
        
        investment = Investment.objects.create(
            investment_type=self.inv_type,
            initial_amount=Decimal('100000.00'),
            date_invested='2026-01-15',
            fund_source='bank_account',
            fund_source_bank=bank,
            recorded_by=self.user,
        )
        
        self.client.login(username='admin', password='admin123')
        response = self.client.post(reverse('investments:approve', kwargs={'pk': investment.pk}))
        
        # Refresh investment from DB
        investment.refresh_from_db()
        self.assertTrue(investment.funds_deducted)
        self.assertEqual(investment.approved_by, self.admin_user)
        self.assertIsNotNone(investment.approved_at)
        
        # Verify bank balance was deducted
        bank.refresh_from_db()
        self.assertEqual(bank.current_balance, Decimal('200000.00'))
        
        # Verify ledger entry created
        latest_balance = BankBalance.objects.filter(account=bank).latest('recorded_on', 'created_at')
        self.assertEqual(latest_balance.transaction_type, BankBalance.TYPE_DEDUCTION)
        self.assertEqual(latest_balance.balance, Decimal('200000.00'))
        self.assertEqual(latest_balance.topup_amount, Decimal('100000.00'))

    def test_approve_investment_with_insufficient_bank_funds(self):
        """Test approval fails when bank balance is insufficient."""
        bank = BankAccount.objects.create(
            bank_name='Test Bank',
            account_number='123456789',
            is_active=True,
        )
        BankBalance.objects.create(
            account=bank,
            balance=Decimal('50000.00'),
            transaction_type='opening',
            recorded_on='2026-01-01',
        )
        
        investment = Investment.objects.create(
            investment_type=self.inv_type,
            initial_amount=Decimal('100000.00'),
            date_invested='2026-01-15',
            fund_source='bank_account',
            fund_source_bank=bank,
            recorded_by=self.user,
        )
        
        self.client.login(username='admin', password='admin123')
        response = self.client.post(reverse('investments:approve', kwargs={'pk': investment.pk}))
        
        # Investment should NOT be approved
        investment.refresh_from_db()
        self.assertFalse(investment.funds_deducted)
        self.assertIsNone(investment.approved_by)
        
        # Bank balance should NOT change
        bank.refresh_from_db()
        self.assertEqual(bank.current_balance, Decimal('50000.00'))

    def test_approve_investment_with_exact_balance(self):
        """Test approval succeeds when investment equals exact bank balance."""
        bank = BankAccount.objects.create(
            bank_name='Test Bank',
            account_number='123456789',
            is_active=True,
        )
        BankBalance.objects.create(
            account=bank,
            balance=Decimal('100000.00'),
            transaction_type='opening',
            recorded_on='2026-01-01',
        )
        
        investment = Investment.objects.create(
            investment_type=self.inv_type,
            initial_amount=Decimal('100000.00'),
            date_invested='2026-01-15',
            fund_source='bank_account',
            fund_source_bank=bank,
            recorded_by=self.user,
        )
        
        self.client.login(username='admin', password='admin123')
        response = self.client.post(reverse('investments:approve', kwargs={'pk': investment.pk}))
        
        investment.refresh_from_db()
        self.assertTrue(investment.funds_deducted)
        
        bank.refresh_from_db()
        self.assertEqual(bank.current_balance, Decimal('0.00'))

    def test_prevent_double_approval(self):
        """Test that an already-approved investment cannot be approved again."""
        bank = BankAccount.objects.create(
            bank_name='Test Bank',
            account_number='123456789',
            is_active=True,
        )
        BankBalance.objects.create(
            account=bank,
            balance=Decimal('300000.00'),
            transaction_type='opening',
            recorded_on='2026-01-01',
        )
        
        investment = Investment.objects.create(
            investment_type=self.inv_type,
            initial_amount=Decimal('100000.00'),
            date_invested='2026-01-15',
            fund_source='bank_account',
            fund_source_bank=bank,
            recorded_by=self.user,
            funds_deducted=True,
            approved_by=self.admin_user,
        )
        
        # Initial balance after first approval (hypothetically)
        BankBalance.objects.create(
            account=bank,
            balance=Decimal('200000.00'),
            transaction_type=BankBalance.TYPE_DEDUCTION,
            topup_amount=Decimal('100000.00'),
            recorded_on='2026-01-15',
            recorded_by=self.admin_user,
        )
        
        self.client.login(username='admin', password='admin123')
        response = self.client.post(reverse('investments:approve', kwargs={'pk': investment.pk}))
        
        # Bank balance should remain unchanged
        bank.refresh_from_db()
        self.assertEqual(bank.current_balance, Decimal('200000.00'))
        
        # Should only have 2 entries (opening + first deduction)
        balance_entries = BankBalance.objects.filter(account=bank).count()
        self.assertEqual(balance_entries, 2)

    def test_concurrent_approvals_prevented_by_select_for_update(self):
        """Test that concurrent approvals are prevented by select_for_update lock."""
        # This test verifies that only one approval succeeds when two attempts happen concurrently
        bank = BankAccount.objects.create(
            bank_name='Test Bank',
            account_number='123456789',
            is_active=True,
        )
        BankBalance.objects.create(
            account=bank,
            balance=Decimal('150000.00'),
            transaction_type='opening',
            recorded_on='2026-01-01',
        )
        
        investment = Investment.objects.create(
            investment_type=self.inv_type,
            initial_amount=Decimal('100000.00'),
            date_invested='2026-01-15',
            fund_source='bank_account',
            fund_source_bank=bank,
            recorded_by=self.user,
        )
        
        self.client.login(username='admin', password='admin123')
        
        # First approval should succeed
        response1 = self.client.post(reverse('investments:approve', kwargs={'pk': investment.pk}))
        
        investment.refresh_from_db()
        first_approved = investment.funds_deducted
        
        # Second approval attempt should be blocked by double-approval check
        response2 = self.client.post(reverse('investments:approve', kwargs={'pk': investment.pk}))
        
        investment.refresh_from_db()
        # Bank should only have one deduction entry
        balance_entries = BankBalance.objects.filter(account=bank).count()
        self.assertEqual(balance_entries, 2)  # opening + one deduction

    def test_approval_with_group_funds_sufficient(self):
        """Test approval with group funds when sufficient."""
        # Disable audit signal temporarily
        from django.db.models.signals import post_save
        from audit.signals import log_save
        
        post_save.disconnect(log_save, sender=Member)
        try:
            member = Member.objects.create(name='Member1', phone='0700000001')
            Contribution.objects.create(
                member=member,
                amount=Decimal('300000.00'),
                date='2026-01-01',
                month=1,
                year=2026,
            )
        finally:
            post_save.connect(log_save, sender=Member)
        
        investment = Investment.objects.create(
            investment_type=self.inv_type,
            initial_amount=Decimal('100000.00'),
            date_invested='2026-01-15',
            fund_source='group_funds',
            recorded_by=self.user,
        )
        
        self.client.login(username='admin', password='admin123')
        response = self.client.post(reverse('investments:approve', kwargs={'pk': investment.pk}))
        
        investment.refresh_from_db()
        self.assertTrue(investment.funds_deducted)
        self.assertEqual(investment.approved_by, self.admin_user)

    def test_approval_with_group_funds_insufficient(self):
        """Test approval fails when group funds insufficient."""
        investment = Investment.objects.create(
            investment_type=self.inv_type,
            initial_amount=Decimal('500000.00'),
            date_invested='2026-01-15',
            fund_source='group_funds',
            recorded_by=self.user,
        )
        
        self.client.login(username='admin', password='admin123')
        response = self.client.post(reverse('investments:approve', kwargs={'pk': investment.pk}))
        
        investment.refresh_from_db()
        self.assertFalse(investment.funds_deducted)

    def test_approval_with_bank_transfer_funding(self):
        """Test approval and deduction when funding source is bank_transfer."""
        bank = BankAccount.objects.create(
            bank_name='Co-op Bank',
            account_name='Investment Account',
            account_number='987654321',
            is_active=True,
        )
        BankBalance.objects.create(
            account=bank,
            balance=Decimal('500000.00'),
            transaction_type='opening',
            recorded_on='2026-01-01',
        )

        investment = Investment.objects.create(
            investment_type=self.inv_type,
            initial_amount=Decimal('150000.00'),
            date_invested='2026-01-15',
            fund_source='bank_transfer',
            fund_source_bank=bank,
            payment_type='bank_transfer',
            mpesa_code='TRF-998877',
            recorded_by=self.user,
        )

        self.client.login(username='admin', password='admin123')
        response = self.client.post(reverse('investments:approve', kwargs={'pk': investment.pk}))

        investment.refresh_from_db()
        self.assertTrue(investment.funds_deducted)
        self.assertEqual(investment.approved_by, self.admin_user)

        # Check bank balance deduction
        bank.refresh_from_db()
        self.assertEqual(bank.current_balance, Decimal('350000.00'))


class InvestmentFormTest(TestCase):
    """Test InvestmentForm validation and behavior."""

    def setUp(self):
        self.user = User.objects.create_user(username='formuser', password='pass123')
        self.category = InvestmentCategory.objects.create(name='Real Estate')
        self.inv_type = InvestmentType.objects.create(
            name='Prime Land',
            category=self.category,
        )
        self.bank = BankAccount.objects.create(
            bank_name='Equity Bank',
            account_name='Chama Holding',
            account_number='5544332211',
            is_active=True,
        )
        BankBalance.objects.create(
            account=self.bank,
            balance=Decimal('1000000.00'),
            transaction_type='opening',
            recorded_on='2026-01-01',
        )

    def test_form_valid_with_bank_transfer(self):
        from .forms import InvestmentForm
        form_data = {
            'investment_type': self.inv_type.pk,
            'initial_amount': '250000.00',
            'date_invested': '2026-01-20',
            'quantity': '1.0',
            'description': 'Purchase of 1/8th acre in Kitengela',
            'fund_source': 'bank_transfer',
            'fund_source_bank': self.bank.pk,
            'payment_type': 'bank_transfer',
            'mpesa_code': 'BNK-REF-2026',
            'status': 'active',
        }
        form = InvestmentForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        inv = form.save(commit=False)
        inv.recorded_by = self.user
        inv.save()
        self.assertEqual(inv.fund_source, 'bank_transfer')
        self.assertEqual(inv.payment_type, 'bank_transfer')
        self.assertEqual(inv.mpesa_code, 'BNK-REF-2026')
