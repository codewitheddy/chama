import datetime
from decimal import Decimal
from django.test import TestCase, Client
from django.utils import timezone
from django.contrib.auth.models import User

from members.models import Member
from welfare.models import (
    WelfareContribution, WelfareContributionRate, WelfareEvent,
    WelfareDisbursement, WelfareSupportContribution, WelfareExternalSupport,
)
from recycle_bin.models import DeletedRecord


class WelfareBulkActionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin_welfare", password="adminpassword123")
        self.member1 = Member.objects.create(name="Welfare Member One", phone="+254711990001")
        self.member2 = Member.objects.create(name="Welfare Member Two", phone="+254711990002")
        self.member3 = Member.objects.create(name="Welfare Member Three", phone="+254711990003")

        today = timezone.localdate()
        self.wc1 = WelfareContribution.objects.create(
            member=self.member1,
            amount=Decimal('500.00'),
            date=today,
            month=1,
            year=today.year,
            payment_type='cash',
        )
        self.wc2 = WelfareContribution.objects.create(
            member=self.member2,
            amount=Decimal('500.00'),
            date=today,
            month=1,
            year=today.year,
            payment_type='cash',
        )
        self.wc3 = WelfareContribution.objects.create(
            member=self.member3,
            amount=Decimal('500.00'),
            date=today,
            month=2,
            year=today.year,
            payment_type='mpesa',
            mpesa_code='WELF123456',
        )

        self.client = Client()
        self.client.force_login(self.user)

    def test_bulk_delete_confirmation_page(self):
        """Posting without confirm=true displays the confirmation page with selected items."""
        response = self.client.post('/welfare/contributions/bulk-delete/', {
            'contribution_ids': f'{self.wc1.pk},{self.wc2.pk}',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Confirm Bulk Welfare Contribution Deletion')
        self.assertContains(response, 'Welfare Member One')
        self.assertContains(response, 'Welfare Member Two')
        self.assertContains(response, 'KES 1,000.00')

    def test_bulk_delete_successful(self):
        """Admin can bulk delete welfare contributions with valid password and reason, saving snapshots to recycle bin."""
        response = self.client.post('/welfare/contributions/bulk-delete/', {
            'confirm': 'true',
            'contribution_ids': f'{self.wc1.pk},{self.wc2.pk}',
            'delete_reason': 'Welfare cleanup test',
            'admin_password': 'adminpassword123',
        }, follow=False)
        self.assertEqual(response.status_code, 302)

        self.assertFalse(WelfareContribution.objects.filter(pk=self.wc1.pk).exists())
        self.assertFalse(WelfareContribution.objects.filter(pk=self.wc2.pk).exists())
        self.assertTrue(WelfareContribution.objects.filter(pk=self.wc3.pk).exists())

        # Check Recycle Bin records
        deleted_records = DeletedRecord.objects.filter(
            model_name='welfarecontribution',
            object_id__in=[str(self.wc1.pk), str(self.wc2.pk)]
        )
        self.assertEqual(deleted_records.count(), 2)
        self.assertEqual(deleted_records.first().delete_reason, 'Welfare cleanup test')

    def test_bulk_delete_wrong_password_fails(self):
        """Wrong password halts bulk deletion and displays error."""
        response = self.client.post('/welfare/contributions/bulk-delete/', {
            'confirm': 'true',
            'contribution_ids': f'{self.wc1.pk}',
            'delete_reason': 'Welfare cleanup test',
            'admin_password': 'wrongpassword',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Incorrect password')
        self.assertTrue(WelfareContribution.objects.filter(pk=self.wc1.pk).exists())

    def test_bulk_delete_missing_reason_fails(self):
        """Missing reason halts bulk deletion and displays error."""
        response = self.client.post('/welfare/contributions/bulk-delete/', {
            'confirm': 'true',
            'contribution_ids': f'{self.wc1.pk}',
            'delete_reason': '',
            'admin_password': 'adminpassword123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A reason for deletion is required')
        self.assertTrue(WelfareContribution.objects.filter(pk=self.wc1.pk).exists())

    def test_bulk_update_month_and_payment_type(self):
        """Bulk update updates month and payment method on all selected welfare contributions."""
        response = self.client.post('/welfare/contributions/bulk-update/', {
            'contribution_ids': f'{self.wc1.pk},{self.wc2.pk}',
            'bulk_month': '6',
            'bulk_year': '2025',
            'bulk_payment_type': 'mpesa',
        }, follow=False)
        self.assertEqual(response.status_code, 302)

        self.wc1.refresh_from_db()
        self.wc2.refresh_from_db()
        self.wc3.refresh_from_db()

        self.assertEqual(self.wc1.month, 6)
        self.assertEqual(self.wc1.year, 2025)
        self.assertEqual(self.wc1.payment_type, 'mpesa')

        self.assertEqual(self.wc2.month, 6)
        self.assertEqual(self.wc2.year, 2025)
        self.assertEqual(self.wc2.payment_type, 'mpesa')

        # wc3 untouched
        self.assertEqual(self.wc3.month, 2)

    def test_bulk_export_csv_and_pdf(self):
        """Exporting with specific IDs only includes selected records."""
        # CSV Export
        response_csv = self.client.post('/welfare/contributions/export/', {
            'ids': f'{self.wc1.pk},{self.wc2.pk}',
            'format': 'csv',
        })
        self.assertEqual(response_csv.status_code, 200)
        self.assertIn('text/csv', response_csv['Content-Type'])
        content = response_csv.content.decode('utf-8')
        self.assertIn('Welfare Member One', content)
        self.assertIn('Welfare Member Two', content)
        self.assertNotIn('Welfare Member Three', content)

        # PDF Export
        response_pdf = self.client.post('/welfare/contributions/export/', {
            'ids': f'{self.wc1.pk},{self.wc2.pk}',
            'format': 'pdf',
        })
        self.assertEqual(response_pdf.status_code, 200)
        self.assertIn('application/pdf', response_pdf['Content-Type'])


class WelfareRateAndContributionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin_rates", password="adminpassword123")
        self.member = Member.objects.create(name="Jane Doe", phone="+254711880001")
        self.client = Client()
        self.client.force_login(self.user)

    def test_rate_creation_and_rate_for_period(self):
        """A rate set on the 21st of October applies to October contributions."""
        import datetime
        r1 = WelfareContributionRate.objects.create(
            amount=Decimal('100.00'),
            effective_date=datetime.date(2026, 4, 29),
        )
        r2 = WelfareContributionRate.objects.create(
            amount=Decimal('200.00'),
            effective_date=datetime.date(2026, 10, 21),
        )

        # September 2026 should use the April rate (100)
        self.assertEqual(WelfareContributionRate.rate_for_period(2026, 9), r1)
        # October 2026 should use the October 21 rate (200)
        self.assertEqual(WelfareContributionRate.rate_for_period(2026, 10), r2)

    def test_welfare_contribution_form_accepts_200(self):
        """WelfareContributionForm accepts 200 when current rate is 200 without 100 cap error."""
        import datetime
        WelfareContributionRate.objects.create(
            amount=Decimal('200.00'),
            effective_date=datetime.date(2026, 10, 1),
        )
        from welfare.forms import WelfareContributionForm
        form = WelfareContributionForm(data={
            'member': self.member.pk,
            'amount': '200.00',
            'date': '2026-10-21',
            'payment_type': 'cash',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_rate_edit_view_with_valid_password(self):
        """Admin can edit an existing rate by providing their admin password."""
        import datetime
        rate = WelfareContributionRate.objects.create(
            amount=Decimal('150.00'),
            effective_date=datetime.date(2026, 8, 1),
        )
        res = self.client.post(f'/welfare/rate/{rate.pk}/edit/', {
            'amount': '250.00',
            'effective_date': '2026-08-01',
            'admin_password': 'adminpassword123',
        }, follow=True)
        self.assertEqual(res.status_code, 200)
        rate.refresh_from_db()
        self.assertEqual(rate.amount, Decimal('250.00'))

    def test_rate_edit_view_with_wrong_password_fails(self):
        """Editing a rate fails and leaves rate untouched if admin password is wrong."""
        import datetime
        rate = WelfareContributionRate.objects.create(
            amount=Decimal('150.00'),
            effective_date=datetime.date(2026, 8, 1),
        )
        res = self.client.post(f'/welfare/rate/{rate.pk}/edit/', {
            'amount': '300.00',
            'effective_date': '2026-08-01',
            'admin_password': 'wrongpassword',
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Incorrect password. Rate update cancelled.')
        rate.refresh_from_db()
        self.assertEqual(rate.amount, Decimal('150.00'))

    def test_rate_edit_view_missing_password_fails(self):
        """Editing a rate fails if admin password is omitted."""
        import datetime
        rate = WelfareContributionRate.objects.create(
            amount=Decimal('150.00'),
            effective_date=datetime.date(2026, 8, 1),
        )
        res = self.client.post(f'/welfare/rate/{rate.pk}/edit/', {
            'amount': '300.00',
            'effective_date': '2026-08-01',
            'admin_password': '',
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Admin password is required')
        rate.refresh_from_db()
        self.assertEqual(rate.amount, Decimal('150.00'))

    def test_rate_delete_view_with_password(self):
        """Admin can delete a rate by providing deletion reason and admin password."""
        import datetime
        rate = WelfareContributionRate.objects.create(
            amount=Decimal('150.00'),
            effective_date=datetime.date(2026, 8, 1),
        )
        res = self.client.post(f'/welfare/rate/{rate.pk}/delete/', {
            'delete_reason': 'Obsolete rate',
            'admin_password': 'adminpassword123',
        }, follow=False)
        self.assertEqual(res.status_code, 302)
        self.assertFalse(WelfareContributionRate.objects.filter(pk=rate.pk).exists())

    def test_rate_delete_view_wrong_password_fails(self):
        """Deleting a rate fails if admin password is wrong."""
        import datetime
        rate = WelfareContributionRate.objects.create(
            amount=Decimal('150.00'),
            effective_date=datetime.date(2026, 8, 1),
        )
        res = self.client.post(f'/welfare/rate/{rate.pk}/delete/', {
            'delete_reason': 'Obsolete rate',
            'admin_password': 'wrongpassword',
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Incorrect password')
        self.assertTrue(WelfareContributionRate.objects.filter(pk=rate.pk).exists())

    def test_non_admin_forbidden_from_edit_and_delete(self):
        """Non-admin users cannot access rate edit or delete endpoints."""
        import datetime
        from accounts.models import UserProfile
        treasurer = User.objects.create_user(username="treasurer_welfare", password="password123")
        treasurer.profile.role = 'treasurer'
        treasurer.profile.save()

        t_client = Client()
        t_client.force_login(treasurer)

        rate = WelfareContributionRate.objects.create(
            amount=Decimal('175.00'),
            effective_date=datetime.date(2026, 7, 1),
        )

        res_edit = t_client.get(f'/welfare/rate/{rate.pk}/edit/')
        self.assertEqual(res_edit.status_code, 403)

        res_delete = t_client.get(f'/welfare/rate/{rate.pk}/delete/')
        self.assertEqual(res_delete.status_code, 403)


class WelfareEventListViewPaginationAndFilterTests(TestCase):
    def setUp(self):
        import datetime
        self.user = User.objects.create_superuser(username="admin_event_test", password="adminpassword123")
        self.client = Client()
        self.client.force_login(self.user)

        self.member1 = Member.objects.create(name="Alpha Member", phone="+254700000001")
        self.member2 = Member.objects.create(name="Beta Member", phone="+254700000002")

        # Create 12 welfare events (7 open, 5 closed)
        for i in range(1, 13):
            status = 'open' if i <= 7 else 'closed'
            beneficiary = self.member1 if i % 2 == 1 else self.member2
            WelfareEvent.objects.create(
                beneficiary=beneficiary,
                description=f"Welfare event description number {i}",
                date_opened=datetime.date(2026, 1, 1) + datetime.timedelta(days=i * 10),
                status=status,
            )

    def test_default_pagination_10_per_page(self):
        """Default page size is 10, so with 12 events page 1 has 10 and page 2 has 2."""
        res = self.client.get('/welfare/events/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.context['events']), 10)
        self.assertTrue(res.context['page_obj'].has_next())
        self.assertEqual(res.context['paginator'].count, 12)
        self.assertEqual(res.context['paginator'].num_pages, 2)
        self.assertContains(res, 'Showing <span class="fw-semibold text-dark">1</span>')
        self.assertContains(res, 'to <span class="fw-semibold text-dark">10</span>')

    def test_custom_per_page_pagination(self):
        """User can specify per_page=5, producing 3 pages."""
        res = self.client.get('/welfare/events/?per_page=5&page=2')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.context['events']), 5)
        self.assertEqual(res.context['paginator'].num_pages, 3)
        self.assertContains(res, 'Showing <span class="fw-semibold text-dark">6</span>')
        self.assertContains(res, 'to <span class="fw-semibold text-dark">10</span>')

    def test_status_filter_open(self):
        """Filtering by status=open returns only the 7 open events."""
        res = self.client.get('/welfare/events/?status=open')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['paginator'].count, 7)
        for ev in res.context['events']:
            self.assertEqual(ev.status, 'open')

    def test_search_filter_by_name(self):
        """Search query q filters across beneficiary name and description."""
        res = self.client.get('/welfare/events/?q=Alpha')
        self.assertEqual(res.status_code, 200)
        for ev in res.context['events']:
            self.assertEqual(ev.beneficiary.name, 'Alpha Member')


class WelfareEventDetailViewPaginationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin_event_detail_test", password="adminpassword123")
        self.client.force_login(self.user)
        self.beneficiary = Member.objects.create(name="Grace Hopper", phone="+254711888999")
        self.event = WelfareEvent.objects.create(
            beneficiary=self.beneficiary,
            description="Medical assistance event for family emergency",
            date_opened=datetime.date(2026, 3, 1),
            status="open",
        )
        # Fund disbursement
        WelfareDisbursement.objects.create(
            event=self.event,
            amount=Decimal('10000.00'),
            date=datetime.date(2026, 3, 2),
            notes="Initial hospital deposit from reserve",
        )
        # 15 member support contributions (page size 10)
        self.contributors = []
        for i in range(1, 16):
            m = Member.objects.create(name=f"Member Supporter {i:02d}", phone=f"+2547220000{i:02d}")
            self.contributors.append(m)
            WelfareSupportContribution.objects.create(
                event=self.event,
                contributor=m,
                amount=Decimal('1000.00'),
                date=datetime.date(2026, 3, 3),
            )
        # 12 external supporters (page size 10)
        for i in range(1, 13):
            WelfareExternalSupport.objects.create(
                event=self.event,
                supporter_name=f"External Supporter {i:02d}",
                supporter_phone=f"+2547330000{i:02d}",
                amount=Decimal('500.00'),
                date=datetime.date(2026, 3, 4),
            )

    def test_event_detail_renders_and_paginates_support_contributions(self):
        # Page 1 (default)
        res = self.client.get(f'/welfare/events/{self.event.pk}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['support_paginator'].count, 15)
        self.assertEqual(res.context['support_paginator'].num_pages, 2)
        self.assertEqual(len(res.context['support_contributions']), 10)
        self.assertEqual(res.context['support_page_obj'].number, 1)

        # Page 2
        res2 = self.client.get(f'/welfare/events/{self.event.pk}/?support_page=2')
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(len(res2.context['support_contributions']), 5)
        self.assertEqual(res2.context['support_page_obj'].number, 2)

    def test_event_detail_paginates_external_support(self):
        # Page 1
        res = self.client.get(f'/welfare/events/{self.event.pk}/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['ext_paginator'].count, 12)
        self.assertEqual(res.context['ext_paginator'].num_pages, 2)
        self.assertEqual(len(res.context['external_support']), 10)

        # Page 2
        res2 = self.client.get(f'/welfare/events/{self.event.pk}/?ext_page=2')
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(len(res2.context['external_support']), 2)
        self.assertEqual(res2.context['ext_page_obj'].number, 2)

    def test_event_detail_percentage_and_totals(self):
        res = self.client.get(f'/welfare/events/{self.event.pk}/')
        self.assertEqual(res.status_code, 200)
        # Fund: 10,000, Members: 15,000, External: 6,000 => Total = 31,000
        self.assertEqual(res.context['event_total'], Decimal('31000.00'))
        self.assertAlmostEqual(res.context['pct_disbursed'], 32.3, delta=0.5)
        self.assertAlmostEqual(res.context['pct_support'], 48.4, delta=0.5)
        self.assertAlmostEqual(res.context['pct_external'], 19.4, delta=0.5)




