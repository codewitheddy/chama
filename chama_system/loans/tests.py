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
        # Create another member for guarantor tests
        self.guarantor = Member.objects.create(name="Guarantor", phone="+254700000002")

    def test_loan_creation_calculations(self):
        """Test that loan creation calculates interest, total, and due date correctly."""
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=date(2024, 1, 15),
        )
        self.assertEqual(loan.interest_amount, Decimal('100.00'))  # 10%
        self.assertEqual(loan.total_payable, Decimal('1100.00'))
        self.assertEqual(loan.late_penalty_per_month, Decimal('100.00'))
        self.assertEqual(loan.late_penalty_months, 0)
        # due date: 1 month later same day (Jan 15 + 1 month = Feb 15)
        self.assertEqual(loan.due_date, date(2024, 2, 15))
        self.assertEqual(loan.status, 'active')

    def test_due_date_month_end(self):
        """Test due date calculation when date_taken is month-end."""
        # Jan 31 + 1 month -> Feb 29 (2024 is leap year) or 28? Let's use 2024-01-31.
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('500.00'),
            duration_months=1,
            date_taken=date(2024, 1, 31),
        )
        # 2024-01-31 + 1 month => 2024-02-31 -> clamped to last day of Feb which is 29 in 2024 (leap year)
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
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=date(2024, 1, 1),
        )
        # Pay full amount
        Payment.objects.create(loan=loan, member=self.member, amount=loan.total_payable, date=date(2024,1,20))
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'cleared')
        self.assertEqual(loan.balance, Decimal('0.00'))

    def test_balance_calculation(self):
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('2000.00'),
            duration_months=3,
            date_taken=date(2024, 1, 1),
        )
        # Pay partial
        Payment.objects.create(loan=loan, member=self.member, amount=Decimal('500.00'), date=date(2024,1,15))
        loan.refresh_from_db()
        expected_balance = loan.total_payable - Decimal('500.00')
        self.assertEqual(loan.balance, expected_balance)

    def test_apply_late_penalty(self):
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=date(2024, 1, 1),
        )
        # Simulate overdue; apply one penalty
        loan.apply_late_penalty()
        loan.refresh_from_db()
        self.assertEqual(loan.late_penalty_months, 1)
        expected_total = Decimal('1000.00') + Decimal('100.00') + Decimal('100.00')  # principal + interest + 1 penalty
        self.assertEqual(loan.total_payable, expected_total)
        self.assertEqual(loan.status, 'late')

    def test_rollover_creates_new_loan_and_marks_old_as_rolled_over(self):
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=date(2024, 1, 1),
        )
        # Pay something so balance is not zero
        Payment.objects.create(loan=loan, member=self.member, amount=Decimal('200.00'), date=date(2024,1,15))
        loan.refresh_from_db()
        outstanding = loan.balance  # should be 1000+100 -200 = 900? Actually total_payable 1100 -200 = 900
        self.assertEqual(outstanding, Decimal('900.00'))

        # Perform rollover
        new_loan = loan.do_rollover(duration_months=3)

        # Old loan should be marked rolled_over
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'rolled_over')
        self.assertEqual(loan.rollover_count, 1)

        # New loan exists and is active
        self.assertIsNotNone(new_loan.pk)
        self.assertEqual(new_loan.status, 'active')
        self.assertEqual(new_loan.loan_amount, outstanding)
        self.assertEqual(new_loan.interest_amount, outstanding * Decimal('0.10'))  # 10%
        self.assertEqual(new_loan.total_payable, outstanding + new_loan.interest_amount)
        self.assertEqual(new_loan.parent_loan, loan)

        # Old loan payments still exist
        self.assertEqual(loan.payment_set.count(), 1)
        # New loan has no payments initially
        self.assertEqual(new_loan.payment_set.count(), 0)

        # Rollover record links both
        rollover = LoanRollover.objects.get(loan=loan)
        self.assertEqual(rollover.new_loan, new_loan)
        self.assertEqual(rollover.balance_before, outstanding)
        self.assertEqual(rollover.new_interest, new_loan.interest_amount)

    def test_rollover_on_fully_paid_loan_raises(self):
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=date(2024, 1, 1),
        )
        Payment.objects.create(loan=loan, member=self.member, amount=loan.total_payable, date=date(2024,1,20))
        loan.refresh_from_db()
        self.assertEqual(loan.balance, Decimal('0.00'))
        with self.assertRaises(ValueError):
            loan.do_rollover()

    def test_payment_delete_updates_status_correctly(self):
        """Test that deleting a payment from a cleared loan reverts status appropriately."""
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=date(2024, 1, 1),
        )
        pay = Payment.objects.create(loan=loan, member=self.member, amount=loan.total_payable, date=date(2024,1,20))
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'cleared')

        # Delete payment
        pay.delete()
        loan.refresh_from_db()
        # Loan should become active (since not yet overdue)
        self.assertEqual(loan.status, 'active')

    def test_payment_delete_on_overdue_loan_sets_late(self):
        """Test that deleting a payment from a late loan keeps it late."""
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=timezone.localdate() - timedelta(days=40),  # 40 days ago => overdue
        )
        # Pay partial to make it not cleared
        pay = Payment.objects.create(loan=loan, member=self.member, amount=Decimal('500.00'), date=date(2024,1,20))
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'late')

        # Delete payment
        pay.delete()
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'late')  # still late due to overdue

    def test_loan_never_becomes_late_after_rollover(self):
        """Rolled over loans should not transition to late even if overdue."""
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=timezone.localdate() - timedelta(days=40),
        )
        # Rollover
        new_loan = loan.do_rollover()
        loan.refresh_from_db()
        self.assertEqual(loan.status, 'rolled_over')

        # Simulate time passing: manually set due_date far in past for loan (old) but it shouldn't matter
        # But ensure that saving old loan doesn't change status
        loan.notes = "test"
        loan.save()
        self.assertEqual(loan.status, 'rolled_over')

    def test_interest_rate_configuration(self):
        """Ensure interest rate from settings is used."""
        from django.conf import settings
        rate = getattr(settings, 'LOAN_INTEREST_RATE', 0.10)
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=date(2024,1,1),
        )
        expected_interest = (Decimal('1000.00') * Decimal(str(rate))).quantize(Decimal('0.01'))
        self.assertEqual(loan.interest_amount, expected_interest)


class LoanRolloverModelTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(name="Member", phone="+254700000003")

    def test_loan_rollover_record_created(self):
        loan = Loan.objects.create(
            member=self.member,
            loan_amount=Decimal('1000.00'),
            duration_months=1,
            date_taken=date(2024,1,1),
        )
        Payment.objects.create(loan=loan, member=self.member, amount=Decimal('200.00'), date=date(2024,1,15))
        loan.refresh_from_db()
        outstanding = loan.balance
        rollover = loan.do_rollover()
        # LoanRollover record
        lr = LoanRollover.objects.get(loan=loan)
        self.assertEqual(lr.balance_before, outstanding)
        self.assertEqual(lr.new_loan, rollover)
        self.assertEqual(lr.new_interest, rollover.interest_amount)
        self.assertEqual(lr.new_total, rollover.total_payable)
