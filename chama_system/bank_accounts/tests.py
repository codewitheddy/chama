from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from bank_accounts.models import BankAccount, BankBalance


class BankAccountTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='treasurer', password='password123')
        self.user.profile.role = 'treasurer'
        self.user.profile.save()
        self.client.login(username='treasurer', password='password123')

    def test_bank_account_create_with_opening_balance(self):
        url = reverse('bank_accounts:add')
        response = self.client.post(url, {
            'bank_name': 'KCB Bank',
            'account_name': 'KCB Main Chama Account',
            'account_number': '1234567890',
            'branch': 'Moi Avenue',
            'is_active': 'on',
            'opening_balance': '50000.00',
            'date': '2026-09-26',
            'notes': 'Initial opening balance',
        })
        self.assertEqual(response.status_code, 302)
        account = BankAccount.objects.get(bank_name='KCB Bank')
        self.assertEqual(account.account_name, 'KCB Main Chama Account')
        self.assertEqual(account.opening_balance, Decimal('50000.00'))
        self.assertEqual(account.current_balance, Decimal('50000.00'))

    def test_bank_account_create_zero_opening_balance(self):
        url = reverse('bank_accounts:add')
        response = self.client.post(url, {
            'bank_name': 'Equity Bank',
            'account_name': 'Equity Operating Account',
            'account_number': '9876543210',
            'branch': 'CBD',
            'is_active': 'on',
            'opening_balance': '0.00',
            'date': '2026-09-26',
            'notes': '',
        })
        self.assertEqual(response.status_code, 302)
        account = BankAccount.objects.get(bank_name='Equity Bank')
        self.assertEqual(account.current_balance, Decimal('0.00'))

    def test_bank_account_add_get_page(self):
        url = reverse('bank_accounts:add')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Register New Bank Account')
        self.assertContains(response, 'Quick Bank Presets')

    def test_bank_account_edit_get_page(self):
        account = BankAccount.objects.create(
            bank_name='NCBA Bank',
            account_name='NCBA Account',
            account_number='999999',
            is_active=True,
        )
        url = reverse('bank_accounts:edit', kwargs={'pk': account.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit Bank Account')
        self.assertContains(response, 'NCBA Bank')

    def test_bank_account_detail_view(self):
        account = BankAccount.objects.create(
            bank_name='KCB Bank',
            account_name='KCB Chama Main Account',
            account_number='1234567890',
            branch='Moi Avenue',
            is_active=True,
        )
        BankBalance.objects.create(
            account=account,
            balance=Decimal('50000.00'),
            topup_amount=Decimal('50000.00'),
            transaction_type=BankBalance.TYPE_OPENING,
            recorded_on='2026-09-26',
            notes='Initial Opening Balance',
        )
        url = reverse('bank_accounts:detail', kwargs={'pk': account.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'KCB Bank')
        self.assertContains(response, 'KCB Chama Main Account')
        self.assertContains(response, 'Account Transaction Ledger')
        self.assertContains(response, 'Record Top-Up / Deposit')
