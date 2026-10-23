from django.test import TestCase
from django.utils import timezone
from decimal import Decimal
from django.contrib.auth.models import User

from members.models import Member, RegistrationFeeRate, RegistrationFeePayment, MemberExit


class MemberModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin", password="password123")
        self.rate = RegistrationFeeRate.objects.create(
            amount=Decimal('1000.00'),
            effective_date=timezone.localdate(),
        )

    def test_registration_fee_sync(self):
        member = Member.objects.create(name="New Member", phone="+254722000001")
        self.assertEqual(member.registration_fee_paid, Decimal('0.00'))

        # Add payment
        fee = RegistrationFeePayment.objects.create(
            member=member,
            amount=Decimal('1000.00'),
            payment_date=timezone.localdate(),
            recorded_by=self.user,
        )
        member.refresh_from_db()
        self.assertEqual(member.registration_fee_paid, Decimal('1000.00'))

        # Delete payment
        fee.delete()
        member.refresh_from_db()
        self.assertEqual(member.registration_fee_paid, Decimal('0.00'))

    def test_member_exit_creation(self):
        member = Member.objects.create(name="Exiting Member", phone="+254722000002")
        exit_rec = MemberExit.objects.create(
            member=member,
            exit_date=timezone.localdate(),
            contributions_returned=Decimal('10000.00'),
            reg_fee_returned=Decimal('1000.00'),
            profit_share_paid=Decimal('2000.00'),
            outstanding_loans_deducted=Decimal('3000.00'),
            outstanding_penalties_deducted=Decimal('0.00'),
            net_payout=Decimal('10000.00'),
            recorded_by=self.user,
        )
        self.assertEqual(str(exit_rec), f"Exiting Member exited on {timezone.localdate()} — KES 10,000.00")


class RegistrationFeeRateFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin_rates", password="password123")
        self.client.force_login(self.user)

    def test_fee_rate_form_effective_date_default_today(self):
        from members.forms import RegistrationFeeRateForm
        form = RegistrationFeeRateForm()
        today = timezone.localdate()
        self.assertEqual(form.fields['effective_date'].initial, today)
        self.assertEqual(form.fields['effective_date'].widget.input_type, 'date')

    def test_fee_rate_add_view_renders_today_date(self):
        response = self.client.get('/members/fee-rate/add/')
        self.assertEqual(response.status_code, 200)
        today_str = timezone.localdate().strftime('%Y-%m-%d')
        self.assertContains(response, f'value="{today_str}"')
        self.assertContains(response, 'type="date"')

    def test_create_fee_rate_successful(self):
        today = timezone.localdate()
        response = self.client.post('/members/fee-rate/add/', {
            'amount': '1500.00',
            'effective_date': today.strftime('%Y-%m-%d'),
            'notes': 'New rate for 2026',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(RegistrationFeeRate.objects.filter(amount=Decimal('1500.00'), effective_date=today).exists())


class RegistrationFeePaymentBulkTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="treasurer_bulk", password="password123")
        self.client.force_login(self.user)

        today = timezone.localdate()
        self.rate = RegistrationFeeRate.objects.create(
            amount=Decimal('1000.00'),
            effective_date=today,
        )

        self.m1 = Member.objects.create(name="Bulk Member One", phone="+254701000001")
        self.m2 = Member.objects.create(name="Bulk Member Two", phone="+254701000002")
        self.m3 = Member.objects.create(name="Bulk Member Three", phone="+254701000003")

    def test_get_bulk_entry_page(self):
        response = self.client.get('/members/fee-payments/bulk/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bulk Registration Fee')
        self.assertContains(response, 'Bulk Member One')
        self.assertContains(response, 'Bulk Member Two')
        self.assertContains(response, 'Bulk Member Three')
        self.assertContains(response, 'KES 1,000')

    def test_post_bulk_entry_successful(self):
        today = timezone.localdate()
        post_data = {
            f'member_{self.m1.pk}_skip': '0',
            f'member_{self.m1.pk}_amount': '1000.00',
            f'member_{self.m1.pk}_date': today.strftime('%Y-%m-%d'),
            f'member_{self.m1.pk}_payment_type': 'cash',
            f'member_{self.m1.pk}_receipt_number': 'RC-001',
            f'member_{self.m1.pk}_notes': 'Paid in full',

            f'member_{self.m2.pk}_skip': '0',
            f'member_{self.m2.pk}_amount': '500.00',
            f'member_{self.m2.pk}_date': today.strftime('%Y-%m-%d'),
            f'member_{self.m2.pk}_payment_type': 'mpesa',
            f'member_{self.m2.pk}_receipt_number': 'MP-002',
            f'member_{self.m2.pk}_notes': 'Deposit 1',

            f'member_{self.m3.pk}_skip': '1',  # skipped
            f'member_{self.m3.pk}_amount': '1000.00',
            f'member_{self.m3.pk}_date': today.strftime('%Y-%m-%d'),
            f'member_{self.m3.pk}_payment_type': 'cash',
        }
        response = self.client.post('/members/fee-payments/bulk/', post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # M1 and M2 should have payments recorded
        self.assertTrue(RegistrationFeePayment.objects.filter(member=self.m1, amount=Decimal('1000.00')).exists())
        self.assertTrue(RegistrationFeePayment.objects.filter(member=self.m2, amount=Decimal('500.00')).exists())
        # M3 should NOT have payment recorded
        self.assertFalse(RegistrationFeePayment.objects.filter(member=self.m3).exists())

        # Check member balances synced
        self.m1.refresh_from_db()
        self.m2.refresh_from_db()
        self.m3.refresh_from_db()
        self.assertEqual(self.m1.registration_fee_paid, Decimal('1000.00'))
        self.assertEqual(self.m2.registration_fee_paid, Decimal('500.00'))
        self.assertEqual(self.m3.registration_fee_paid, Decimal('0.00'))

    def test_post_bulk_entry_validation_error(self):
        today = timezone.localdate()
        post_data = {
            f'member_{self.m1.pk}_skip': '0',
            f'member_{self.m1.pk}_amount': '-50.00',  # invalid
            f'member_{self.m1.pk}_date': today.strftime('%Y-%m-%d'),
            f'member_{self.m1.pk}_payment_type': 'cash',
        }
        response = self.client.post('/members/fee-payments/bulk/', post_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Enter a valid amount greater than zero')
        self.assertFalse(RegistrationFeePayment.objects.filter(member=self.m1).exists())


class MemberExpectedReturnTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin_return", password="password123")
        self.client.force_login(self.user)
        self.member = Member.objects.create(name="Savings Member", phone="+254700000001", is_active=True)

    def test_total_penalties_unpaid(self):
        from penalties.models import Penalty
        self.assertEqual(self.member.total_penalties_unpaid(), Decimal('0.00'))

        # Add unpaid penalty
        Penalty.objects.create(
            member=self.member,
            amount=Decimal('300.00'),
            date=timezone.localdate(),
            reason='Late',
            paid=False,
        )
        # Add paid penalty
        Penalty.objects.create(
            member=self.member,
            amount=Decimal('500.00'),
            date=timezone.localdate(),
            reason='Absence',
            paid=True,
            paid_date=timezone.localdate(),
        )
        self.assertEqual(self.member.total_penalties_unpaid(), Decimal('300.00'))

    def test_expected_return_deducts_loans_and_penalties(self):
        """
        User request scenario:
        Member has saving of 5,000 and a loan of 5,500.
        The system should check and always less penalties and loans from expected returns.
        """
        from contributions.models import Contribution
        from loans.models import Loan
        from penalties.models import Penalty

        # Savings = 5,000
        Contribution.objects.create(
            member=self.member,
            amount=Decimal('5000.00'),
            date=timezone.localdate(),
            month=1,
            year=2026,
        )
        # Loan with balance = 5,500
        Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('5000.00'),
            interest_rate=Decimal('0.10'),
            total_payable=Decimal('5500.00'),
            amount_paid=Decimal('0.00'),
            status='active',
            date_taken=timezone.localdate(),
            due_date=timezone.localdate(),
        )
        # Unpaid penalty = 200
        Penalty.objects.create(
            member=self.member,
            amount=Decimal('200.00'),
            date=timezone.localdate(),
            reason='Late meeting',
            paid=False,
        )

        response = self.client.get(f'/members/{self.member.pk}/')
        self.assertEqual(response.status_code, 200)

        preview = response.context['yearend_preview']
        self.assertIsNotNone(preview)
        self.assertEqual(preview['principal_back'], Decimal('5000.00'))
        self.assertEqual(preview['outstanding_loans'], Decimal('5500.00'))
        self.assertEqual(preview['outstanding_penalties'], Decimal('200.00'))
        self.assertEqual(preview['total_deductions'], Decimal('5700.00'))
        # Total expected return must be 0.00 because loan + penalty (5700) exceeds savings (5000)
        self.assertEqual(preview['total'], Decimal('0.00'))
        self.assertEqual(preview['deficit'], Decimal('700.00'))

        # Also check HTML template contains deduction lines and deficit alert
        self.assertContains(response, 'Less: Outstanding Loan')
        self.assertContains(response, 'Less: Unpaid Penalties')
        self.assertContains(response, 'Loan/Penalty Deficit:')



