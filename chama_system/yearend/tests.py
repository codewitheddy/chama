from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from decimal import Decimal
from datetime import date

from members.models import Member
from contributions.models import Contribution
from loans.models import Loan
from penalties.models import Penalty
from other_income.models import OtherIncome
from expenses.models import Expense, ExpenseCategory
from yearend.models import YearEndWithdrawal, MemberInterestShare, YearEndMemberStatus
from yearend.views import _compute_year_end_distribution

User = get_user_model()


class YearEndDistributionTests(TestCase):
    def setUp(self):
        self.treasurer = User.objects.create_user(
            username='treasurer_user',
            password='testpassword123',
            email='treasurer@test.com',
        )
        self.treasurer.profile.role = 'treasurer'
        self.treasurer.profile.save()

        self.client = Client()
        self.client.login(username='treasurer_user', password='testpassword123')

        # Create members
        self.member1 = Member.objects.create(
            name='Alice Member',
            phone='0711000001',
            registration_fee_paid=Decimal('1000.00'),
            is_active=True,
        )
        self.member2 = Member.objects.create(
            name='Bob Member',
            phone='0711000002',
            registration_fee_paid=Decimal('1000.00'),
            is_active=True,
        )

        # Alice contributed 30,000, Bob contributed 10,000 (Total = 40,000; Alice has 75%, Bob has 25%)
        Contribution.objects.create(
            member=self.member1,
            amount=Decimal('30000.00'),
            date=date(2026, 1, 15),
            month=1,
            year=2026,
        )
        Contribution.objects.create(
            member=self.member2,
            amount=Decimal('10000.00'),
            date=date(2026, 1, 15),
            month=1,
            year=2026,
        )

        # Loan with interest: 10,000 loan, 12,000 payable (2,000 interest), fully paid
        Loan.objects.create(
            member=self.member1,
            loan_amount=Decimal('10000.00'),
            interest_rate=Decimal('0.20'),
            total_payable=Decimal('12000.00'),
            amount_paid=Decimal('12000.00'),
            status='cleared',
            date_taken=date(2026, 2, 1),
            due_date=date(2026, 6, 1),
        )

        # Penalties: 1,000 paid
        Penalty.objects.create(
            member=self.member2,
            amount=Decimal('1000.00'),
            date=date(2026, 3, 1),
            reason='Late attendance',
            paid=True,
            paid_date=date(2026, 3, 1),
        )

        # Other Income: 4,000 external grant
        OtherIncome.objects.create(
            source='External Grant',
            amount=Decimal('4000.00'),
            date=date(2026, 4, 1),
            description='Community Grant',
        )

        # Group Fund Expense: 500 meeting stationery
        cat = ExpenseCategory.objects.create(name='Office & Meeting')
        Expense.objects.create(
            category=cat,
            description='Meeting Stationery',
            amount=Decimal('500.00'),
            date=date(2026, 5, 1),
            fund_source='group_funds',
            recorded_by=self.treasurer,
        )

    def test_default_distribution_policy(self):
        """
        Default: include_loan_interest=True (2000), include_penalties=True (1000),
        include_other_income=False (0 shared, 4000 retained),
        include_registration_fees=False (0 shared, 2000 retained),
        deduct_expenses=True (-500).
        Gross selected = 2000 + 1000 = 3000.
        Profit pool = 3000 - 500 = 2500.
        Retained funds = 4000 (other) + 2000 (reg fees) = 6000.
        Principal back = 40000 (Alice 30k, Bob 10k).
        Total payout = 40000 + 2500 = 42500.
        Alice share (75%) = 1875.00, Bob share (25%) = 625.00.
        """
        members = [self.member1, self.member2]
        d = _compute_year_end_distribution(members)

        self.assertEqual(d['distributable_profit_pool'], Decimal('2500.00'))
        self.assertEqual(d['retained_funds'], Decimal('6000.00'))
        self.assertEqual(d['total_principal_back'], Decimal('40000.00'))
        self.assertEqual(d['total_payout'], Decimal('42500.00'))

        alice_row = next(r for r in d['member_breakdown'] if r['member'] == self.member1)
        bob_row = next(r for r in d['member_breakdown'] if r['member'] == self.member2)

        self.assertEqual(alice_row['interest_share'], Decimal('1875.00'))
        self.assertEqual(alice_row['total'], Decimal('31875.00'))
        self.assertEqual(bob_row['interest_share'], Decimal('625.00'))
        self.assertEqual(bob_row['total'], Decimal('10625.00'))

    def test_include_other_income_and_registration_fees(self):
        """
        When group chooses to share Other Income (+4000) and Registration Fees (+2000):
        Gross selected = 2000 (loan interest) + 1000 (penalties) + 4000 (other) + 2000 (reg fees) = 9000.
        Profit pool = 9000 - 500 = 8500.
        Retained funds = 0.
        """
        members = [self.member1, self.member2]
        d = _compute_year_end_distribution(
            members,
            include_loan_interest=True,
            include_penalties=True,
            include_other_income=True,
            include_registration_fees=True,
            deduct_expenses=True,
        )

        self.assertEqual(d['distributable_profit_pool'], Decimal('8500.00'))
        self.assertEqual(d['retained_funds'], Decimal('0.00'))
        self.assertEqual(d['total_payout'], Decimal('48500.00'))

    def test_accumulate_all_revenue(self):
        """
        When group chooses to retain all revenue for next year (unchecking all revenue checkboxes):
        Profit pool = 0.
        Retained funds = 2000 + 1000 + 4000 + 2000 = 9000.
        Total payout = 40000 (Principal only).
        """
        members = [self.member1, self.member2]
        d = _compute_year_end_distribution(
            members,
            include_loan_interest=False,
            include_penalties=False,
            include_other_income=False,
            include_registration_fees=False,
            include_investment_returns=False,
            deduct_expenses=False,
        )

        self.assertEqual(d['distributable_profit_pool'], Decimal('0.00'))
        self.assertEqual(d['retained_funds'], Decimal('9000.00'))
        self.assertEqual(d['total_payout'], Decimal('40000.00'))

    def test_preview_view_get(self):
        url = reverse('yearend:preview')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Distributable Revenue Streams')
        self.assertContains(response, 'Retained for Next Year')

    def test_preview_pdf_view_get(self):
        url = reverse('yearend:preview_pdf')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_create_yearend_withdrawal_with_policy(self):
        url = reverse('yearend:create')
        post_data = {
            'financial_year': 2026,
            'date': '2026-12-31',
            'notes': '2026 Annual General Meeting distribution',
            'include_loan_interest': 'on',
            'include_penalties': 'on',
            # other_income not checked
            # registration_fees not checked
            'include_investment_returns': 'on',
            'deduct_expenses': 'on',
            f'status_{self.member1.pk}': 'continuing',
            f'status_{self.member2.pk}': 'continuing',
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302)

        withdrawal = YearEndWithdrawal.objects.get(financial_year=2026)
        self.assertEqual(withdrawal.amount_withdrawn, Decimal('42500.00'))
        self.assertEqual(withdrawal.interest_shared, Decimal('2500.00'))
        self.assertEqual(withdrawal.retained_funds, Decimal('6000.00'))
        self.assertTrue(withdrawal.include_loan_interest)
        self.assertTrue(withdrawal.include_penalties)
        self.assertFalse(withdrawal.include_other_income)
        self.assertFalse(withdrawal.include_registration_fees)

        # Check detail page
        detail_url = reverse('yearend:detail', kwargs={'pk': withdrawal.pk})
        detail_res = self.client.get(detail_url)
        self.assertEqual(detail_res.status_code, 200)
        self.assertContains(detail_res, 'Retained for Next Year')
        self.assertContains(detail_res, 'KES 6,000.00')

        # Check PDF export
        pdf_url = reverse('yearend:export_pdf', kwargs={'pk': withdrawal.pk})
        pdf_res = self.client.get(pdf_url)
        self.assertEqual(pdf_res.status_code, 200)
        self.assertEqual(pdf_res['Content-Type'], 'application/pdf')

    def test_deduct_loans_and_penalties_from_distribution(self):
        """
        Verify that for member with savings of 5,000 and loan of 5,500:
        The system checks and lesses loans and penalties from expected returns.
        If deductions exceed gross return, total is 0.00 and deficit is tracked.
        """
        # Create a member with 5,000 savings
        debtor = Member.objects.create(
            name='Debtor Member',
            phone='0711000003',
            is_active=True,
        )
        Contribution.objects.create(
            member=debtor,
            amount=Decimal('5000.00'),
            date=date(2026, 1, 15),
            month=1,
            year=2026,
        )
        # Create active loan with 5,500 balance (loan 5000, payable 5500, paid 0)
        Loan.objects.create(
            member=debtor,
            loan_amount=Decimal('5000.00'),
            interest_rate=Decimal('0.10'),
            total_payable=Decimal('5500.00'),
            amount_paid=Decimal('0.00'),
            status='active',
            date_taken=date(2026, 2, 1),
            due_date=date(2026, 6, 1),
        )
        # Add an unpaid penalty of 200
        Penalty.objects.create(
            member=debtor,
            amount=Decimal('200.00'),
            date=date(2026, 3, 1),
            reason='Meeting Absence',
            paid=False,
        )

        members = [self.member1, self.member2, debtor]
        d = _compute_year_end_distribution(members)

        debtor_row = next(r for r in d['member_breakdown'] if r['member'] == debtor)
        self.assertEqual(debtor_row['principal_back'], Decimal('5000.00'))
        self.assertEqual(debtor_row['outstanding_loans'], Decimal('5500.00'))
        self.assertEqual(debtor_row['outstanding_penalties'], Decimal('200.00'))
        self.assertEqual(debtor_row['total_deductions'], Decimal('5700.00'))
        
        # Gross return = 5000 + profit share
        gross = debtor_row['principal_back'] + debtor_row['interest_share']
        self.assertEqual(debtor_row['gross_return'], gross)
        # Since deductions (5700) > gross (5000 + ~277), total payout is 0.00
        self.assertEqual(debtor_row['total'], Decimal('0.00'))
        self.assertEqual(debtor_row['deficit'], Decimal('5700.00') - gross)
        self.assertTrue(debtor_row['deficit'] > 0)

