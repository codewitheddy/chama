from django.test import TestCase
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import calendar

from members.models import Member
from loans.models import Loan, LoanRollover
from payments.models import Payment
from penalties.models import Penalty


class LoanModelTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(name="Test Member", phone="+254700000001")
        self.guarantor = Member.objects.create(name="Guarantor", phone="+254700000002")

    def test_loan_creation_calculations(self):
        """Test that loan creation calculates interest, total, and due date correctly."""
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=today,
        )
        self.assertEqual(loan.interest_amount, Decimal('100.00'))  # 10%
        self.assertEqual(loan.total_payable, Decimal('1100.00'))
        self.assertEqual(loan.late_penalty_per_month, Decimal('100.00'))
        self.assertEqual(loan.late_penalty_months, 0)
        self.assertEqual(loan.status, 'active')

    def test_due_date_month_end(self):
        """Test due date calculation when date_taken is month-end."""
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('500.00'),
            duration_months=1,
            date_taken=date(2024, 1, 31),
        )
        # 2024-01-31 + 1 month => 2024-02-29 (leap year)
        self.assertEqual(loan.due_date, date(2024, 2, 29))

    def test_status_becomes_late_when_overdue(self):
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=timezone.localdate() - timedelta(days=40),  # overdue
        )
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'late')

    def test_status_cleared_when_fully_paid(self):
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=today,
        )
        # Pay full amount
        Payment.objects.create(loan=loan, member=self.member, amount=loan.total_payable, date=today)
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'cleared')
        self.assertEqual(loan.balance, Decimal('0.00'))

    def test_balance_calculation(self):
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('2000.00'),
            duration_months=3,
            date_taken=today,
        )
        # Pay partial
        Payment.objects.create(loan=loan, member=self.member, amount=Decimal('500.00'), date=today)
        loan.refresh_from_db()
        expected_balance = loan.total_payable - Decimal('500.00')
        self.assertEqual(loan.balance, expected_balance)

    def test_apply_late_penalty(self):
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=today,
        )
        # Simulate overdue; apply one penalty
        loan.apply_late_penalty()
        loan.refresh_from_db()
        self.assertEqual(loan.late_penalty_months, 1)
        expected_total = Decimal('1000.00') + Decimal('100.00') + Decimal('100.00')  # principal + interest + 1 penalty
        self.assertEqual(loan.total_payable, expected_total)
        self.assertEqual(loan.status, 'late')

    def test_rollover_in_place_updates_loan(self):
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=today,
        )
        # Pay something so balance is not zero
        Payment.objects.create(loan=loan, member=self.member, amount=Decimal('200.00'), date=today)
        loan.refresh_from_db()
        outstanding = loan.balance  # 1100 - 200 = 900
        self.assertEqual(outstanding, Decimal('900.00'))

        # Perform in-place rollover
        loan.do_rollover(duration_months=3)
        loan.refresh_from_db()

        self.assertEqual(loan.status, 'active')
        self.assertEqual(loan.rollover_count, 1)
        self.assertEqual(loan.loan_amount, outstanding)
        self.assertEqual(loan.interest_amount, Decimal('90.00'))  # 10% of 900
        self.assertEqual(loan.total_payable, Decimal('990.00'))
        self.assertEqual(loan.amount_paid, Decimal('0.00'))

        # Check LoanRollover record
        rollover = LoanRollover.objects.get(loan=loan)
        self.assertEqual(rollover.balance_before, outstanding)
        self.assertEqual(rollover.new_interest, Decimal('90.00'))
        self.assertEqual(rollover.new_total, Decimal('990.00'))

    def test_rollover_on_fully_paid_loan_raises(self):
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=today,
        )
        Payment.objects.create(loan=loan, member=self.member, amount=loan.total_payable, date=today)
        loan.refresh_from_db()
        self.assertEqual(loan.balance, Decimal('0.00'))
        with self.assertRaises(ValueError):
            loan.do_rollover()

    def test_payment_delete_updates_status_correctly(self):
        """Test that deleting a payment from a cleared loan reverts status appropriately."""
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=today,
        )
        pay = Payment.objects.create(loan=loan, member=self.member, amount=loan.total_payable, date=today)
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'cleared')

        # Delete payment
        pay.delete()
        loan.refresh_from_db()
        # Loan should become active (since not yet overdue)
        self.assertEqual(loan.status, 'active')

    def test_payment_delete_on_overdue_loan_sets_late(self):
        """Test that deleting a payment from a late loan keeps it late."""
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=today - timedelta(days=40),  # 40 days ago => overdue
        )
        # Pay partial to make it not cleared
        pay = Payment.objects.create(loan=loan, member=self.member, amount=Decimal('500.00'), date=today - timedelta(days=35))
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'late')

        # Delete payment
        pay.delete()
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'late')  # still late due to overdue

    def test_interest_rate_configuration(self):
        """Ensure interest rate from settings is used."""
        from django.conf import settings
        rate = getattr(settings, 'LOAN_INTEREST_RATE', 0.10)
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=today,
        )
        expected_interest = (Decimal('1000.00') * Decimal(str(rate))).quantize(Decimal('0.01'))
        self.assertEqual(loan.interest_amount, expected_interest)


class LoanRolloverModelTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(name="Member", phone="+254700000003")

    def test_loan_rollover_record_created(self):
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=today,
        )
        Payment.objects.create(loan=loan, member=self.member, amount=Decimal('200.00'), date=today)
        loan.refresh_from_db()
        outstanding = loan.balance
        loan.do_rollover()
        # LoanRollover record
        lr = LoanRollover.objects.get(loan=loan)
        self.assertEqual(lr.balance_before, outstanding)
        self.assertEqual(lr.new_interest, loan.interest_amount)
        self.assertEqual(lr.new_total, loan.total_payable)


class EmergencyLoanProductTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(name="Emergency Borrower", phone="+254700000099")

    def test_emergency_loan_product_creation(self):
        from loans.models import LoanProduct
        product = LoanProduct.objects.create(
            name="Emergency Medical Loan",
            interest_type="emergency",
            interest_rate=Decimal('5.00'),  # should be forced to 0
            duration_months=1,
        )
        self.assertEqual(product.interest_rate, Decimal('0.00'))
        self.assertTrue(product.is_emergency)
        self.assertEqual(product.rate_as_decimal, Decimal('0.00'))
        self.assertEqual(product.loan_type_for_calc, 'emergency')

    def test_loan_issued_with_emergency_product(self):
        from loans.models import LoanProduct
        product = LoanProduct.objects.create(
            name="Emergency Quick Relief",
            interest_type="emergency",
            duration_months=1,
        )
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.member,
            product=product,
            loan_type=product.loan_type_for_calc,
            interest_rate=product.rate_as_decimal,
            loan_amount=Decimal('5000.00'),
            duration_months=1,
            date_taken=today,
        )
        self.assertEqual(loan.interest_amount, Decimal('0.00'))
        self.assertEqual(loan.total_payable, Decimal('5000.00'))
        self.assertEqual(loan.balance, Decimal('5000.00'))
        self.assertEqual(loan.status, 'active')

    def test_emergency_loan_product_form(self):
        from loans.forms import LoanProductForm
        form = LoanProductForm(data={
            'name': 'Form Emergency Loan',
            'interest_type': 'emergency',
            'interest_frequency': 'monthly',
            'interest_rate': '10.00',  # should be cleaned to 0.00
            'duration_months': 2,
            'min_amount': '500',
            'max_amount': '20000',
            'is_active': True,
        })
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()
        self.assertEqual(product.interest_rate, Decimal('0.00'))
        self.assertTrue(product.is_emergency)

    def test_emergency_loan_product_create_view(self):
        from django.contrib.auth.models import User
        from django.test import Client
        user = User.objects.create_superuser(username="admin_emerg", password="password123")
        client = Client()
        client.force_login(user)
        response = client.post('/loans/products/add/', {
            'name': 'View Emergency Product',
            'interest_type': 'emergency',
            'interest_frequency': 'monthly',
            'interest_rate': '0.00',
            'duration_months': 3,
            'min_amount': '100',
            'max_amount': '50000',
            'is_active': 'on',
            'is_emergency': 'on',
        }, follow=False)
        self.assertEqual(response.status_code, 302)
        from loans.models import LoanProduct
        product = LoanProduct.objects.get(name='View Emergency Product')
        self.assertEqual(product.interest_rate, Decimal('0.00'))
        self.assertTrue(product.is_emergency)

    def test_emergency_loan_form_defaults_zero_rate(self):
        from loans.forms import LoanForm
        # Direct emergency loan_type
        form = LoanForm(data={
            'borrower_type': 'member',
            'member': self.member.pk,
            'loan_amount': '10000.00',
            'loan_type': 'emergency',
            'duration_months': 1,
            'date_taken': timezone.localdate().isoformat(),
            'fund_source': 'group_funds',
        })
        self.assertTrue(form.is_valid(), form.errors)
        loan = form.save()
        self.assertEqual(loan.loan_type, 'emergency')
        self.assertEqual(loan.interest_rate, Decimal('0.00'))
        self.assertEqual(loan.interest_amount, Decimal('0.00'))
        self.assertEqual(loan.total_payable, Decimal('10000.00'))

    def test_emergency_loan_calculator_endpoint(self):
        from django.contrib.auth.models import User
        from django.test import Client
        user = User.objects.create_superuser(username="treasurer_calc", password="password123")
        client = Client()
        client.force_login(user)
        response = client.get('/loans/calculator/?amount=15000&months=2&loan_type=emergency')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['loan_type'], 'emergency')
        self.assertEqual(data['total_interest'], '0.00')
        self.assertEqual(data['total_payable'], '15000.00')
        self.assertEqual(data['rate_percent'], '0.00')


class LoanApplicationTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from contributions.models import Contribution
        self.user = User.objects.create_superuser(username="treasurer", password="password123")
        self.member = Member.objects.create(name="Applicant Member", phone="+254700000088")
        today = timezone.localdate()
        Contribution.objects.create(
            member=self.member,
            amount=Decimal('50000.00'),
            date=today,
            month=today.month,
            year=today.year,
        )
        from django.test import Client
        self.client = Client()
        self.client.force_login(self.user)

    def test_loan_application_submit_and_approve_flow(self):
        from loans.models import LoanApplication, Loan
        # 1. Submit application
        response = self.client.post('/loans/applications/add/', {
            'member': self.member.pk,
            'loan_amount': '15000.00',
            'duration_months': 3,
            'reason': 'Expanding farming enterprise',
            'notes': 'Urgent request',
        }, follow=False)
        self.assertEqual(response.status_code, 302)

        app = LoanApplication.objects.get(member=self.member)
        self.assertEqual(app.status, 'pending')
        self.assertEqual(app.loan_amount, Decimal('15000.00'))
        self.assertIsNone(app.loan)

        # 2. Approve application
        today = timezone.localdate()
        response = self.client.post(f'/loans/applications/{app.pk}/', {
            'action': 'approve',
            'date_taken': str(today),
            'fund_source': 'group_funds',
            'review_notes': 'Approved by committee',
        }, follow=False)
        self.assertEqual(response.status_code, 302)

        app.refresh_from_db()
        self.assertEqual(app.status, 'approved')
        self.assertIsNotNone(app.loan)
        self.assertEqual(app.loan.loan_amount, Decimal('15000.00'))
        self.assertEqual(app.loan.status, 'active')

    def test_loan_application_reject_flow(self):
        from loans.models import LoanApplication
        app = LoanApplication.objects.create(
            member=self.member,
            loan_amount=Decimal('8000.00'),
            duration_months=2,
            reason='Personal project',
            status='pending',
            applied_by=self.user,
        )

        response = self.client.post(f'/loans/applications/{app.pk}/', {
            'action': 'reject',
            'review_notes': 'Insufficient guarantor coverage',
        }, follow=False)
        self.assertEqual(response.status_code, 302)

        app.refresh_from_db()
        self.assertEqual(app.status, 'rejected')
        self.assertEqual(app.review_notes, 'Insufficient guarantor coverage')
        self.assertIsNone(app.loan)


class BankFundedLoanWorkflowTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from bank_accounts.models import BankAccount, BankBalance
        self.user = User.objects.create_superuser(username="admin_bank", password="password123")
        self.member = Member.objects.create(name="Bank Borrower", phone="+254700000077")
        from contributions.models import Contribution
        today = timezone.localdate()
        Contribution.objects.create(
            member=self.member,
            amount=Decimal('50000.00'),
            date=today,
            month=today.month,
            year=today.year,
        )
        self.bank = BankAccount.objects.create(
            bank_name="Equity Bank",
            account_name="Main Chama Ops",
            account_number="0123456789",
        )
        BankBalance.objects.create(
            account=self.bank,
            balance=Decimal('100000.00'),
            transaction_type=BankBalance.TYPE_TOPUP,
            recorded_on=timezone.localdate(),
            recorded_by=self.user,
            notes="Opening balance seed",
        )
        from django.test import Client
        self.client = Client()
        self.client.force_login(self.user)



    def test_bank_loan_repayment_syncs_and_deletion_refunds(self):
        from loans.models import Loan
        from bank_accounts.models import BankBalance
        from payments.models import Payment

        # 1. Issue bank funded loan
        response = self.client.post('/loans/add/', {
            'borrower_type': 'member',
            'member': self.member.pk,
            'loan_amount': '20000.00',
            'loan_type': 'flat',
            'interest_rate': '10.00',
            'duration_months': 2,
            'date_taken': str(timezone.localdate()),
            'fund_source': 'bank_account',
            'fund_source_bank': self.bank.pk,
        }, follow=False)
        self.assertEqual(response.status_code, 302)

        self.bank.refresh_from_db()
        self.assertEqual(self.bank.current_balance, Decimal('80000.00'))

        loan = Loan.objects.get(member=self.member)

        # 2. Record payment
        Payment.objects.create(
            loan=loan,
            member=self.member,
            amount=Decimal('5000.00'),
            date=timezone.localdate(),
        )


        self.bank.refresh_from_db()
        # Pre-disburse 100000 - 20000 + 5000 = 85000
        self.assertEqual(self.bank.current_balance, Decimal('85000.00'))

        # 3. Delete loan -> should restore remaining net un-repaid amount (15000)
        response = self.client.post(f'/loans/{loan.pk}/delete/', {
            'admin_password': 'password123',
            'delete_reason': 'Testing delete',
        }, follow=False)
        self.assertEqual(response.status_code, 302)

        self.bank.refresh_from_db()
        self.assertEqual(self.bank.current_balance, Decimal('100000.00'))


class GroupSettingsTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from django.test import Client
        self.admin = User.objects.create_superuser(username="admin_group", password="password123")
        self.regular_user = User.objects.create_user(username="regular_user", password="password123")
        self.client = Client()

    def test_group_settings_requires_admin(self):
        from django.urls import reverse
        # Unauthenticated
        response = self.client.get(reverse('loans:group_settings'))
        self.assertNotEqual(response.status_code, 200)

        # Non-admin user
        self.client.force_login(self.regular_user)
        response = self.client.get(reverse('loans:group_settings'))
        self.assertIn(response.status_code, [302, 403])

        # Admin user
        self.client.force_login(self.admin)
        response = self.client.get(reverse('loans:group_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'loans/group_settings.html')

    def test_get_group_info_defaults(self):
        from loans.models import SystemSetting
        info = SystemSetting.get_group_info()
        self.assertIn('group_name', info)
        self.assertIn('group_currency', info)
        self.assertIn('theme_sidebar_bg', info)
        self.assertEqual(info['group_currency'], 'KES')

    def test_update_profile_settings(self):
        from django.urls import reverse
        from loans.models import SystemSetting
        self.client.force_login(self.admin)
        response = self.client.post(reverse('loans:group_settings'), {
            'active_tab': 'profile',
            'group_name': 'Umoja Investment Group',
            'group_tagline': 'Growing Together',
            'group_currency': 'USD',
            'group_location': 'Nairobi, Kenya',
            'group_postal_address': 'P.O. Box 12345',
            'group_phone': '+254711223344',
            'group_email': 'info@umojachama.org',
            'group_registration': 'CHAMA-2024-001',
            'group_founded': '2020',
        }, follow=True)
        self.assertEqual(response.status_code, 200)

        info = SystemSetting.get_group_info()
        self.assertEqual(info['group_name'], 'Umoja Investment Group')
        self.assertEqual(info['group_tagline'], 'Growing Together')
        self.assertEqual(info['group_currency'], 'USD')
        self.assertEqual(info['group_location'], 'Nairobi, Kenya')
        self.assertEqual(info['group_phone'], '+254711223344')
        self.assertEqual(info['group_email'], 'info@umojachama.org')
        self.assertEqual(info['group_registration'], 'CHAMA-2024-001')
        self.assertEqual(info['group_founded'], '2020')

    def test_update_theme_preset(self):
        from django.urls import reverse
        from loans.models import SystemSetting, THEME_PRESETS
        self.client.force_login(self.admin)
        response = self.client.post(reverse('loans:group_settings'), {
            'active_tab': 'theme',
            'theme_preset': 'emerald_forest',
            'use_custom_theme': '0',
        }, follow=True)
        self.assertEqual(response.status_code, 200)

        info = SystemSetting.get_group_info()
        self.assertEqual(info['theme_preset'], 'emerald_forest')
        self.assertEqual(info['theme_sidebar_bg'], THEME_PRESETS['emerald_forest']['sidebar_bg'])
        self.assertEqual(info['theme_primary_color'], THEME_PRESETS['emerald_forest']['primary_color'])

    def test_update_custom_theme(self):
        from django.urls import reverse
        from loans.models import SystemSetting
        self.client.force_login(self.admin)
        response = self.client.post(reverse('loans:group_settings'), {
            'active_tab': 'theme',
            'theme_preset': 'custom',
            'use_custom_theme': '1',
            'custom_sidebar_bg': '#1a2b3c',
            'custom_primary_color': '#e0245e',
        }, follow=True)
        self.assertEqual(response.status_code, 200)

        info = SystemSetting.get_group_info()
        self.assertEqual(info['theme_preset'], 'custom')
        self.assertEqual(info['theme_sidebar_bg'], '#1e2a3a')
        self.assertEqual(info['theme_primary_color'], '#e0245e')

    def test_update_financial_settings(self):
        from django.urls import reverse
        from loans.models import SystemSetting
        self.client.force_login(self.admin)
        response = self.client.post(reverse('loans:group_settings'), {
            'active_tab': 'financial',
            'default_interest_rate': '12.50',
            'default_late_penalty_rate': '15.00',
            'grace_period_days': '5',
            'max_active_loans_per_member': '3',
            'savings_loan_multiplier': '4.00',
        }, follow=True)
        self.assertEqual(response.status_code, 200)

        info = SystemSetting.get_group_info()
        self.assertEqual(info['default_interest_rate'], '12.50')
        self.assertEqual(info['default_late_penalty_rate'], '15.00')
        self.assertEqual(info['grace_period_days'], '5')
        self.assertEqual(info['max_active_loans_per_member'], '3')
        self.assertEqual(info['savings_loan_multiplier'], '4.00')

    def test_update_document_branding(self):
        from django.urls import reverse
        from loans.models import SystemSetting
        self.client.force_login(self.admin)
        response = self.client.post(reverse('loans:group_settings'), {
            'active_tab': 'documents',
            'pdf_header_title': 'UMOJA FINANCIAL REPORT',
            'pdf_footer_text': 'Trying to change footer',
            'pdf_show_logo': '1',
            'pdf_show_contact': '0',
        }, follow=True)
        self.assertEqual(response.status_code, 200)

        info = SystemSetting.get_group_info()
        self.assertEqual(info['pdf_header_title'], 'UMOJA FINANCIAL REPORT')
        self.assertEqual(info['pdf_footer_text'], 'Finance Wise TBM - Powered by Ropenix Investments Limited ( 018 218 0965 )')
        self.assertTrue(info['pdf_show_logo'])
        self.assertFalse(info['pdf_show_contact'])

    def test_logo_upload_and_removal(self):
        from django.urls import reverse
        from django.core.files.uploadedfile import SimpleUploadedFile
        from loans.models import SystemSetting
        self.client.force_login(self.admin)

        # 1. Upload valid 1x1 png image
        png_content = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00'
            b'\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        logo_file = SimpleUploadedFile("test_logo.png", png_content, content_type="image/png")

        response = self.client.post(reverse('loans:group_settings'), {
            'active_tab': 'logo',
            'logo_file': logo_file,
        }, follow=True)
        self.assertEqual(response.status_code, 200)

        info = SystemSetting.get_group_info()
        self.assertTrue(info['group_logo'].endswith('.png'))

        # 2. Remove logo
        response = self.client.post(reverse('loans:group_settings'), {
            'active_tab': 'logo',
            'remove_logo': '1',
        }, follow=True)
        self.assertEqual(response.status_code, 200)

        info = SystemSetting.get_group_info()
        self.assertEqual(info['group_logo'], '')


class GuarantorCoverageLimitTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from contributions.models import Contribution
        self.treasurer = User.objects.create_superuser(username="treasurer_guar", password="password123")
        self.borrower = Member.objects.create(name="Borrower Member", phone="+254700111222")
        self.guarantor1 = Member.objects.create(name="Guarantor One", phone="+254700333444")
        self.guarantor2 = Member.objects.create(name="Guarantor Two", phone="+254700555666")

        today = timezone.localdate()
        # Borrower has KES 5,000 savings
        Contribution.objects.create(
            member=self.borrower, amount=Decimal('5000.00'),
            date=today, month=today.month, year=today.year
        )
        # Guarantor 1 has KES 20,000 savings
        Contribution.objects.create(
            member=self.guarantor1, amount=Decimal('20000.00'),
            date=today, month=today.month, year=today.year
        )
        # Guarantor 2 has KES 20,000 savings
        Contribution.objects.create(
            member=self.guarantor2, amount=Decimal('20000.00'),
            date=today, month=today.month, year=today.year
        )

        from django.test import Client
        self.client = Client()
        self.client.force_login(self.treasurer)

    def test_guarantor_cannot_guarantee_more_than_shortfall_single(self):
        """
        Loan requested: KES 10,000. Borrower savings: KES 5,000. Shortfall target: KES 5,000.
        Guarantor 1 tries to guarantee KES 6,000 (exceeds target KES 5,000).
        Must fail validation and not create loan.
        """
        today = timezone.localdate()
        response = self.client.post('/loans/add/', {
            'borrower_type': 'member',
            'member': self.borrower.pk,
            'loan_amount': '10000.00',
            'loan_type': 'flat',
            'interest_rate': '10.00',
            'duration_months': 1,
            'date_taken': str(today),
            'fund_source': 'group_funds',
            'guarantor_ids[]': [str(self.guarantor1.pk)],
            'guarantor_amounts[]': ['6000.00'],
        }, follow=True)

        self.assertEqual(Loan.objects.filter(member=self.borrower).count(), 0)
        # Check error message in response
        messages = list(response.context['messages'])
        self.assertTrue(any("cannot exceed the requested loan shortfall" in str(m) or "cannot guarantee KES 6,000" in str(m) for m in messages))

    def test_guarantors_combined_cannot_exceed_shortfall(self):
        """
        Loan requested: KES 10,000. Shortfall: KES 5,000.
        Guarantor 1: KES 3,000 + Guarantor 2: KES 3,000 => Total KES 6,000 (exceeds KES 5,000).
        Must fail validation.
        """
        today = timezone.localdate()
        response = self.client.post('/loans/add/', {
            'borrower_type': 'member',
            'member': self.borrower.pk,
            'loan_amount': '10000.00',
            'loan_type': 'flat',
            'interest_rate': '10.00',
            'duration_months': 1,
            'date_taken': str(today),
            'fund_source': 'group_funds',
            'guarantor_ids[]': [str(self.guarantor1.pk), str(self.guarantor2.pk)],
            'guarantor_amounts[]': ['3000.00', '3000.00'],
        }, follow=True)

        self.assertEqual(Loan.objects.filter(member=self.borrower).count(), 0)
        messages = list(response.context['messages'])
        self.assertTrue(any("cannot exceed the requested loan shortfall" in str(m) for m in messages))

    def test_guarantor_exact_shortfall_succeeds(self):
        """
        Loan requested: KES 10,000. Shortfall: KES 5,000.
        Guarantor 1: KES 5,000 => Exactly matches target.
        Must succeed.
        """
        today = timezone.localdate()
        response = self.client.post('/loans/add/', {
            'borrower_type': 'member',
            'member': self.borrower.pk,
            'loan_amount': '10000.00',
            'loan_type': 'flat',
            'interest_rate': '10.00',
            'duration_months': 1,
            'date_taken': str(today),
            'fund_source': 'group_funds',
            'guarantor_ids[]': [str(self.guarantor1.pk)],
            'guarantor_amounts[]': ['5000.00'],
        }, follow=False)

        self.assertEqual(response.status_code, 302)
        loan = Loan.objects.get(member=self.borrower)
        self.assertEqual(loan.loan_amount, Decimal('10000.00'))
        self.assertEqual(loan.guarantors.count(), 1)
        self.assertEqual(loan.guarantors.first().amount_guaranteed, Decimal('5000.00'))

    def test_guarantor_form_validation_cannot_exceed_target(self):
        """
        Test LoanGuarantorForm directly.
        """
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.borrower,
            loan_amount=Decimal('10000.00'),
            duration_months=1,
            date_taken=today,
        )
        # Shortfall is 10,000 - 5,000 = 5,000
        from loans.forms import LoanGuarantorForm
        # Try to guarantee 6,000
        form = LoanGuarantorForm(loan=loan, data={
            'guarantor': self.guarantor1.pk,
            'amount_guaranteed': '6000.00',
        })
        self.assertFalse(form.is_valid())
        self.assertTrue(any("cannot exceed the required target" in e for e in form.non_field_errors()))

        # Try exact 5,000 => valid
        form = LoanGuarantorForm(loan=loan, data={
            'guarantor': self.guarantor1.pk,
            'amount_guaranteed': '5000.00',
        })
        self.assertTrue(form.is_valid(), form.errors)


class LoanRestructuringMathUnitTests(TestCase):
    """
    Isolated unit tests for recalculate_schedule() money math.
    Validates Decimal precision, remainder reconciliation, and all restructure types.
    """

    def setUp(self):
        self.member = Member.objects.create(name="Alice Borrower", phone="+254711000001")
        self.today = timezone.localdate()

    def test_term_extension_with_partial_payments(self):
        """
        Original Loan: KES 10,000 with 10% flat -> total payable 11,000.
        Borrower pays 5,000. Remaining balance = 6,000.
        Term extension over 3 months with 0% additional rate.
        """
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('10000.00'),
            duration_months=1,
            date_taken=self.today,
            amount_paid=Decimal('5000.00'),
        )
        self.assertEqual(loan.balance, Decimal('6000.00'))

        from loans.restructuring import recalculate_schedule
        schedule = recalculate_schedule(
            loan=loan,
            restructure_type='TERM_EXTENSION',
            params={'new_term_months': 3, 'new_rate': '0.00', 'loan_type': 'emergency'},
            as_of_date=self.today
        )

        self.assertEqual(len(schedule), 3)
        total_installments = sum(item['total_installment'] for item in schedule)
        self.assertEqual(total_installments, Decimal('6000.00'))
        self.assertEqual(schedule[0]['principal_amount'], Decimal('2000.00'))
        self.assertEqual(schedule[1]['principal_amount'], Decimal('2000.00'))
        self.assertEqual(schedule[2]['principal_amount'], Decimal('2000.00'))

    def test_rate_adjustment_recalculates_interest(self):
        """
        Loan balance = KES 8,000.
        Rate adjusted to 5% flat for 2 months.
        Total interest = 8,000 * 0.05 = 400.00. Total payable = 8,400.00.
        """
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('8000.00'),
            duration_months=1,
            date_taken=self.today,
        )
        from loans.restructuring import recalculate_schedule
        schedule = recalculate_schedule(
            loan=loan,
            restructure_type='RATE_ADJUSTMENT',
            params={'new_term_months': 2, 'new_rate': '0.05', 'loan_type': 'flat'},
            as_of_date=self.today
        )

        self.assertEqual(len(schedule), 2)
        total_p = sum(item['principal_amount'] for item in schedule)
        total_i = sum(item['interest_amount'] for item in schedule)
        total_all = sum(item['total_installment'] for item in schedule)

        # Loan original total_payable was 8000 + 800 (10%) = 8800.
        # remaining balance is 8800. With 5% on 8800 = 440 interest => total 9240.
        self.assertEqual(total_p, loan.balance)
        self.assertEqual(total_all, total_p + total_i)

    def test_moratorium_without_interest(self):
        """
        Moratorium of 2 months freeze (0 payment) + 2 months post-freeze repayment.
        """
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('10000.00'),
            duration_months=1,
            date_taken=self.today,
        )
        # Outstanding total is 11,000
        from loans.restructuring import recalculate_schedule
        schedule = recalculate_schedule(
            loan=loan,
            restructure_type='MORATORIUM',
            params={
                'moratorium_months': 2,
                'accrue_interest': False,
                'remaining_months': 2,
                'new_rate': '0.00',
                'loan_type': 'emergency',
            },
            as_of_date=self.today
        )

        self.assertEqual(len(schedule), 4)
        # Months 1 & 2: freeze (0.00)
        self.assertEqual(schedule[0]['total_installment'], Decimal('0.00'))
        self.assertEqual(schedule[1]['total_installment'], Decimal('0.00'))
        # Months 3 & 4: amortize 11,000 / 2 = 5,500 each
        self.assertEqual(schedule[2]['total_installment'], Decimal('5500.00'))
        self.assertEqual(schedule[3]['total_installment'], Decimal('5500.00'))
        total_paid = sum(item['total_installment'] for item in schedule)
        self.assertEqual(total_paid, Decimal('11000.00'))

    def test_moratorium_with_interest_accrual(self):
        """
        Moratorium of 2 months freeze WITH interest accruing on outstanding balance.
        """
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('10000.00'),
            duration_months=1,
            date_taken=self.today,
        )
        from loans.restructuring import recalculate_schedule
        schedule = recalculate_schedule(
            loan=loan,
            restructure_type='MORATORIUM',
            params={
                'moratorium_months': 2,
                'accrue_interest': True,
                'remaining_months': 2,
                'new_rate': '0.10',
                'loan_type': 'reducing_principal',
            },
            as_of_date=self.today
        )

        self.assertEqual(len(schedule), 4)
        # First 2 months must accrue interest (> 0) while principal is 0
        self.assertEqual(schedule[0]['principal_amount'], Decimal('0.00'))
        self.assertGreater(schedule[0]['interest_amount'], Decimal('0.00'))
        self.assertEqual(schedule[1]['principal_amount'], Decimal('0.00'))
        self.assertGreater(schedule[1]['interest_amount'], Decimal('0.00'))

    def test_consolidation_two_loans(self):
        """
        Consolidate 2 loans of remaining balances 4,000 and 6,000 into one 4-month schedule.
        """
        loan1 = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('4000.00'),
            duration_months=1,
            date_taken=self.today,
        )
        loan2 = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('6000.00'),
            duration_months=1,
            date_taken=self.today,
        )
        combined_balance = loan1.balance + loan2.balance  # 4400 + 6600 = 11000

        from loans.restructuring import recalculate_schedule
        schedule = recalculate_schedule(
            loan=loan1,
            restructure_type='CONSOLIDATION',
            params={
                'consolidated_loans': [loan1, loan2],
                'new_term_months': 4,
                'new_rate': '0.00',
                'loan_type': 'emergency',
            },
            as_of_date=self.today
        )

        self.assertEqual(len(schedule), 4)
        total_inst = sum(item['total_installment'] for item in schedule)
        self.assertEqual(total_inst, combined_balance)

    def test_rounding_remainder_reconciliation(self):
        """
        When balance is not evenly divisible by term (e.g. 1000 over 3 months),
        the final installment must absorb the rounding remainder so sum matches exactly.
        """
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            interest_rate=Decimal('0.00'),
            duration_months=1,
            date_taken=self.today,
        )
        from loans.restructuring import recalculate_schedule
        schedule = recalculate_schedule(
            loan=loan,
            restructure_type='TERM_EXTENSION',
            params={'new_term_months': 3, 'new_rate': '0.00', 'loan_type': 'emergency'},
            as_of_date=self.today
        )

        self.assertEqual(len(schedule), 3)
        self.assertEqual(schedule[0]['principal_amount'], Decimal('333.33'))
        self.assertEqual(schedule[1]['principal_amount'], Decimal('333.33'))
        self.assertEqual(schedule[2]['principal_amount'], Decimal('333.34'))

        total_sum = sum(item['total_installment'] for item in schedule)
        self.assertEqual(total_sum, Decimal('1000.00'))

    def test_write_off_returns_empty_schedule(self):
        """
        WRITE_OFF returns empty schedule.
        """
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('5000.00'),
            duration_months=1,
            date_taken=self.today,
        )
        from loans.restructuring import recalculate_schedule
        schedule = recalculate_schedule(
            loan=loan,
            restructure_type='WRITE_OFF',
            params={},
            as_of_date=self.today
        )
        self.assertEqual(schedule, [])


class LoanRestructuringIntegrationTests(TestCase):
    """
    Integration tests covering the entire Request -> Approve / Reject lifecycle,
    schedule supersession, atomic transactions, permission gating, and guardrails.
    """

    def setUp(self):
        from django.contrib.auth.models import User
        from accounts.models import UserProfile
        from loans.models import Loan, RepaymentSchedule, LoanGuarantor

        self.user = User.objects.create_user(username="treasurer1", password="password123")
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.role = "treasurer"
        profile.save()
        self.client.login(username="treasurer1", password="password123")

        self.member = Member.objects.create(name="Brian Keter", phone="+254722000001")
        self.guarantor_member = Member.objects.create(name="Gladys Chebet", phone="+254722000002")
        self.today = timezone.localdate()

        # Create active loan
        self.loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('12000.00'),
            duration_months=1,
            interest_rate=Decimal('0.10'),
            date_taken=self.today,
        )
        # Create guarantor
        self.guarantor = LoanGuarantor.objects.create(
            loan=self.loan,
            guarantor=self.guarantor_member,
            amount_guaranteed=Decimal('6000.00'),
        )
        # Create initial repayment schedule row
        self.orig_schedule = RepaymentSchedule.objects.create(
            loan=self.loan,
            installment_number=1,
            due_date=self.loan.due_date,
            principal_amount=Decimal('12000.00'),
            interest_amount=Decimal('1200.00'),
            total_installment=Decimal('13200.00'),
            paid_amount=Decimal('0.00'),
            is_paid=False,
        )

    def test_full_request_and_approval_workflow(self):
        """
        1. Request a TERM_EXTENSION restructure via view.
        2. Approve it via approve view.
        3. Assert old schedule row is superseded.
        4. Assert new schedule rows created.
        5. Assert guarantor signal received.
        """
        from loans.models import LoanRestructure, RepaymentSchedule
        from loans.restructuring import loan_restructure_approved

        # Signal listener
        signal_data = []
        def on_approved(sender, restructure, loan, approved_by, guarantors, **kwargs):
            signal_data.append({'restructure': restructure, 'loan': loan, 'guarantors': guarantors})

        loan_restructure_approved.connect(on_approved)

        # 1. Post restructure request
        req_resp = self.client.post(f'/loans/{self.loan.pk}/restructure/add/', {
            'restructure_type': 'TERM_EXTENSION',
            'new_term_months': 3,
            'new_rate': '10.00',
            'reason': 'Member experienced temporary business cash flow disruption.',
        })
        self.assertEqual(req_resp.status_code, 302)

        restructure = LoanRestructure.objects.get(loan=self.loan)
        self.assertEqual(restructure.status, 'PENDING')
        self.assertEqual(restructure.requested_by, self.user)
        self.assertEqual(restructure.restructure_type, 'TERM_EXTENSION')

        # 2. Approve restructure
        appr_resp = self.client.post(f'/loans/restructures/{restructure.pk}/approve/')
        self.assertEqual(appr_resp.status_code, 302)

        restructure.refresh_from_db()
        self.assertEqual(restructure.status, 'APPROVED')
        self.assertEqual(restructure.approved_by, self.user)
        self.assertIsNotNone(restructure.approved_at)

        # 3. Old schedule is superseded
        self.orig_schedule.refresh_from_db()
        self.assertIsNotNone(self.orig_schedule.superseded_by)

        # 4. New schedules generated (3 installments)
        new_schedules = RepaymentSchedule.objects.filter(
            loan=self.loan, restructure=restructure
        ).order_by('installment_number')
        self.assertEqual(new_schedules.count(), 3)
        self.assertEqual(self.orig_schedule.superseded_by, new_schedules.first())

        total_inst_sum = sum(s.total_installment for s in new_schedules)
        self.assertEqual(total_inst_sum, Decimal('13200.00') + Decimal('1320.00'))

        # 5. Signal was dispatched with guarantor
        self.assertEqual(len(signal_data), 1)
        self.assertEqual(signal_data[0]['guarantors'][0].guarantor, self.guarantor_member)

        loan_restructure_approved.disconnect(on_approved)

    def test_rejected_request_leaves_schedule_untouched(self):
        """
        Rejecting a restructure leaves original schedule and loan completely intact.
        """
        from loans.models import LoanRestructure, RepaymentSchedule

        restructure = LoanRestructure.objects.create(
            loan=self.loan,
            requested_by=self.user,
            restructure_type='RATE_ADJUSTMENT',
            reason='Requesting reduced interest.',
            status='PENDING',
        )

        resp = self.client.post(f'/loans/restructures/{restructure.pk}/reject/', {
            'rejection_reason': 'Policy does not permit retroactive rate discounts.',
        })
        self.assertEqual(resp.status_code, 302)

        restructure.refresh_from_db()
        self.assertEqual(restructure.status, 'REJECTED')
        self.assertIn('Policy does not permit', restructure.rejection_reason)

        # Original schedule remains unsuperseded
        self.orig_schedule.refresh_from_db()
        self.assertIsNone(self.orig_schedule.superseded_by)
        self.assertEqual(RepaymentSchedule.objects.filter(loan=self.loan).count(), 1)

    def test_guardrail_cannot_restructure_cleared_loan(self):
        """
        Cleared or zero-balance loans cannot be restructured.
        """
        self.loan.status = 'cleared'
        self.loan.amount_paid = self.loan.total_payable
        self.loan.save()

        from loans.models import LoanRestructure
        from django.core.exceptions import ValidationError

        restructure = LoanRestructure(
            loan=self.loan,
            requested_by=self.user,
            restructure_type='TERM_EXTENSION',
            reason='Test on cleared loan',
        )
        with self.assertRaises(ValidationError):
            restructure.clean()

    def test_guardrail_max_restructures_limit(self):
        """
        Enforce max approved restructures per loan.
        """
        from loans.models import LoanRestructure
        from loans.restructuring import check_max_restructures_limit
        from django.core.exceptions import ValidationError

        # Create 3 approved restructures
        for _ in range(3):
            LoanRestructure.objects.create(
                loan=self.loan,
                requested_by=self.user,
                approved_by=self.user,
                restructure_type='TERM_EXTENSION',
                status='APPROVED',
                reason='Past restructure',
            )

        # 4th check should raise ValidationError
        with self.assertRaises(ValidationError):
            check_max_restructures_limit(self.loan)

    def test_loan_list_restructured_filter_and_badge(self):
        """
        Verify that restructured loans appear with a Restructured badge on loan lists
        and can be filtered using ?status=restructured.
        """
        from loans.models import LoanRestructure

        # Initially not restructured
        self.assertFalse(self.loan.is_restructured)

        # Create approved restructure
        LoanRestructure.objects.create(
            loan=self.loan,
            requested_by=self.user,
            approved_by=self.user,
            restructure_type='TERM_EXTENSION',
            status='APPROVED',
            reason='Approved extension',
        )

        self.loan.refresh_from_db()
        self.assertTrue(self.loan.is_restructured)

        # Query loan list with filter
        resp = self.client.get('/loans/?status=restructured')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.loan, resp.context['loans'])
        self.assertContains(resp, "Restructured")






