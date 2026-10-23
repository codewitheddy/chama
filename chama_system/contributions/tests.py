from django.test import TestCase, Client
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal

from members.models import Member
from contributions.models import Contribution
from recycle_bin.models import DeletedRecord


class ContributionModelTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(name="Contributor Member", phone="+254733000001")

    def test_contribution_defaults(self):
        today = timezone.localdate()
        c = Contribution.objects.create(
            member=self.member,
            amount=Decimal('1500.00'),
            date=today,
            month=today.month,
        )
        self.assertEqual(c.year, today.year)
        self.assertEqual(c.payment_type, 'cash')
        self.assertEqual(str(c), f"Contributor Member - {c.get_month_display()} {today.year}")


class BulkContributionActionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin_contrib", password="adminpassword123")
        self.member1 = Member.objects.create(name="Member One", phone="+254711000001")
        self.member2 = Member.objects.create(name="Member Two", phone="+254711000002")
        self.member3 = Member.objects.create(name="Member Three", phone="+254711000003")

        today = timezone.localdate()
        self.c1 = Contribution.objects.create(
            member=self.member1,
            amount=Decimal('1000.00'),
            date=today,
            month=1,
            year=today.year,
            payment_type='cash',
        )
        self.c2 = Contribution.objects.create(
            member=self.member2,
            amount=Decimal('2000.00'),
            date=today,
            month=1,
            year=today.year,
            payment_type='cash',
        )
        self.c3 = Contribution.objects.create(
            member=self.member3,
            amount=Decimal('3000.00'),
            date=today,
            month=2,
            year=today.year,
            payment_type='mpesa',
            mpesa_code='QWE1234567',
        )

        self.client = Client()
        self.client.force_login(self.user)

    def test_bulk_delete_confirmation_page(self):
        """Posting without confirm=true displays the confirmation page with selected items."""
        response = self.client.post('/contributions/bulk-delete/', {
            'contribution_ids': f'{self.c1.pk},{self.c2.pk}',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Confirm Bulk Contribution Deletion')
        self.assertContains(response, 'Member One')
        self.assertContains(response, 'Member Two')
        self.assertContains(response, 'KES 3,000.00')  # 1000 + 2000

    def test_bulk_delete_successful(self):
        """Admin can bulk delete contributions with valid password and reason, saving snapshots to recycle bin."""
        response = self.client.post('/contributions/bulk-delete/', {
            'confirm': 'true',
            'contribution_ids': f'{self.c1.pk},{self.c2.pk}',
            'delete_reason': 'Batch cleanup test',
            'admin_password': 'adminpassword123',
        }, follow=False)
        self.assertEqual(response.status_code, 302)

        self.assertFalse(Contribution.objects.filter(pk=self.c1.pk).exists())
        self.assertFalse(Contribution.objects.filter(pk=self.c2.pk).exists())
        self.assertTrue(Contribution.objects.filter(pk=self.c3.pk).exists())

        # Check Recycle Bin records
        deleted_records = DeletedRecord.objects.filter(
            model_name='contribution',
            object_id__in=[str(self.c1.pk), str(self.c2.pk)]
        )
        self.assertEqual(deleted_records.count(), 2)
        self.assertEqual(deleted_records.first().delete_reason, 'Batch cleanup test')

    def test_bulk_delete_wrong_password_fails(self):
        """Wrong password halts bulk deletion and displays error."""
        response = self.client.post('/contributions/bulk-delete/', {
            'confirm': 'true',
            'contribution_ids': f'{self.c1.pk}',
            'delete_reason': 'Batch cleanup test',
            'admin_password': 'wrongpassword',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Incorrect password')
        self.assertTrue(Contribution.objects.filter(pk=self.c1.pk).exists())

    def test_bulk_delete_missing_reason_fails(self):
        """Missing reason halts bulk deletion and displays error."""
        response = self.client.post('/contributions/bulk-delete/', {
            'confirm': 'true',
            'contribution_ids': f'{self.c1.pk}',
            'delete_reason': '',
            'admin_password': 'adminpassword123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A reason for deletion is required')
        self.assertTrue(Contribution.objects.filter(pk=self.c1.pk).exists())

    def test_bulk_update_month_and_payment_type(self):
        """Bulk update updates month and payment method on all selected contributions."""
        response = self.client.post('/contributions/bulk-update/', {
            'contribution_ids': f'{self.c1.pk},{self.c2.pk}',
            'bulk_month': '5',
            'bulk_year': '2025',
            'bulk_payment_type': 'mpesa',
        }, follow=False)
        self.assertEqual(response.status_code, 302)

        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c3.refresh_from_db()

        self.assertEqual(self.c1.month, 5)
        self.assertEqual(self.c1.year, 2025)
        self.assertEqual(self.c1.payment_type, 'mpesa')

        self.assertEqual(self.c2.month, 5)
        self.assertEqual(self.c2.year, 2025)
        self.assertEqual(self.c2.payment_type, 'mpesa')

        # c3 remains untouched
        self.assertEqual(self.c3.month, 2)
        self.assertEqual(self.c3.payment_type, 'mpesa')

    def test_bulk_export_csv_and_pdf(self):
        """Exporting with specific IDs only includes selected records."""
        # CSV Export
        response_csv = self.client.post('/contributions/export/', {
            'ids': f'{self.c1.pk},{self.c2.pk}',
            'format': 'csv',
        })
        self.assertEqual(response_csv.status_code, 200)
        self.assertIn('text/csv', response_csv['Content-Type'])
        content = response_csv.content.decode('utf-8')
        self.assertIn('Member One', content)
        self.assertIn('Member Two', content)
        self.assertNotIn('Member Three', content)

        # PDF Export
        response_pdf = self.client.post('/contributions/export/', {
            'ids': f'{self.c1.pk}',
            'format': 'pdf',
        })
        self.assertEqual(response_pdf.status_code, 200)
        self.assertIn('application/pdf', response_pdf['Content-Type'])

    def test_contribution_list_cash_and_mpesa_breakdown(self):
        """Contribution list view returns accurate Cash and M-Pesa totals and percentages."""
        response = self.client.get('/contributions/')
        self.assertEqual(response.status_code, 200)

        # Grand totals: c1(1000 cash) + c2(2000 cash) + c3(3000 mpesa) = 6000 total
        self.assertEqual(response.context['grand_total'], Decimal('6000.00'))
        self.assertEqual(response.context['grand_count'], 3)
        self.assertEqual(response.context['grand_cash_total'], Decimal('3000.00'))
        self.assertEqual(response.context['grand_cash_count'], 2)
        self.assertEqual(response.context['grand_mpesa_total'], Decimal('3000.00'))
        self.assertEqual(response.context['grand_mpesa_count'], 1)
        self.assertEqual(response.context['grand_cash_pct'], 50.0)
        self.assertEqual(response.context['grand_mpesa_pct'], 50.0)

        # HTML includes Cash and M-Pesa metrics
        self.assertContains(response, 'Cash Collections')
        self.assertContains(response, 'M-Pesa Collections')
        self.assertContains(response, 'Channel Distribution')

    def test_contribution_list_payment_type_filtering(self):
        """Filtering by payment_type returns only matching contributions and updates filtered subtotals."""
        # Filter Cash
        response_cash = self.client.get('/contributions/?payment_type=cash')
        self.assertEqual(response_cash.status_code, 200)
        contribs_cash = list(response_cash.context['contributions'])
        self.assertEqual(len(contribs_cash), 2)
        self.assertIn(self.c1, contribs_cash)
        self.assertIn(self.c2, contribs_cash)
        self.assertNotIn(self.c3, contribs_cash)
        self.assertEqual(response_cash.context['filtered_total'], Decimal('3000.00'))
        self.assertEqual(response_cash.context['filtered_cash_total'], Decimal('3000.00'))
        self.assertEqual(response_cash.context['filtered_mpesa_total'], Decimal('0.00'))

        # Filter M-Pesa
        response_mpesa = self.client.get('/contributions/?payment_type=mpesa')
        self.assertEqual(response_mpesa.status_code, 200)
        contribs_mpesa = list(response_mpesa.context['contributions'])
        self.assertEqual(len(contribs_mpesa), 1)
        self.assertIn(self.c3, contribs_mpesa)
        self.assertEqual(response_mpesa.context['filtered_total'], Decimal('3000.00'))
        self.assertEqual(response_mpesa.context['filtered_cash_total'], Decimal('0.00'))
        self.assertEqual(response_mpesa.context['filtered_mpesa_total'], Decimal('3000.00'))

