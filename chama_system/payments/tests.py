from django.test import TestCase
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

from members.models import Member
from loans.models import Loan, NonMemberApplicant
from payments.models import Payment


class PaymentModelTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(name="Borrower Member", phone="+254711000001")
        self.non_member = NonMemberApplicant.objects.create(
            full_name="External Applicant",
            phone="+254799000001",
            qualification_status="qualified",
        )

    def test_member_payment_creation_updates_loan(self):
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=today,
        )
        self.assertEqual(loan.amount_paid, Decimal('0.00'))

        p = Payment.objects.create(
            loan=loan,
            member=self.member,
            amount=Decimal('300.00'),
            date=today,
        )
        loan.refresh_from_db()
        self.assertEqual(loan.amount_paid, Decimal('300.00'))
        self.assertEqual(loan.balance, Decimal('800.00'))
        self.assertEqual(str(p), f"Borrower Member - KES 300.00 on {today}")

    def test_non_member_payment_creation(self):
        today = timezone.localdate()
        loan = Loan.objects.create(
            borrower_type='non_member',
            non_member=self.non_member,
            loan_amount=Decimal('2000.00'),
            duration_months=1,
            date_taken=today,
        )
        p = Payment.objects.create(
            loan=loan,
            member=None,
            amount=Decimal('500.00'),
            date=today,
        )
        loan.refresh_from_db()
        self.assertEqual(loan.amount_paid, Decimal('500.00'))
        self.assertEqual(str(p), f"External Applicant - KES 500.00 on {today}")

    def test_rollover_and_payment_scoping(self):
        """Payments before rollover must not be summed into post-rollover amount_paid."""
        today = timezone.localdate()
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=today - timedelta(days=30),
        )
        # Pre-rollover payment
        Payment.objects.create(
            loan=loan,
            member=self.member,
            amount=Decimal('400.00'),
            date=today - timedelta(days=15),
        )
        loan.refresh_from_db()
        self.assertEqual(loan.amount_paid, Decimal('400.00'))
        self.assertEqual(loan.balance, Decimal('700.00'))

        # Rollover
        loan.do_rollover(duration_months=2)
        loan.refresh_from_db()
        self.assertEqual(loan.loan_amount, Decimal('700.00'))
        self.assertEqual(loan.amount_paid, Decimal('0.00'))
        self.assertEqual(loan.total_payable, Decimal('770.00'))

        # Post-rollover payment
        Payment.objects.create(
            loan=loan,
            member=self.member,
            amount=Decimal('200.00'),
            date=today,
        )
        loan.refresh_from_db()
        # Should only be 200, NOT 400 + 200 = 600
        self.assertEqual(loan.amount_paid, Decimal('200.00'))
        self.assertEqual(loan.balance, Decimal('570.00'))
