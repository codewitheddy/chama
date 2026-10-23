from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal

from members.models import Member
from contributions.models import Contribution
from loans.models import Loan, LoanApplication
from penalties.models import Penalty


class DashboardAndNotificationsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin_dash", password="adminpassword123")
        self.client = Client()
        self.client.force_login(self.user)

        self.member = Member.objects.create(name="Sample Member", phone="+254700000000", is_active=True)
        today = timezone.localdate()

        Contribution.objects.create(
            member=self.member,
            amount=Decimal('500.00'),
            date=today,
            month=today.month,
            year=today.year,
            payment_type='cash',
        )

        Penalty.objects.create(
            member=self.member,
            reason="Late Attendance",
            amount=Decimal('100.00'),
            date=today,
            paid=False,
        )

    def test_dashboard_index(self):
        url = reverse('dashboard:dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_dashboard_notifications_view(self):
        url = reverse('dashboard:notifications')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('total_alert_count', response.context)
        self.assertIn('shares_compliance_pct', response.context)
        self.assertIn('welfare_compliance_pct', response.context)

    def test_dashboard_notifications_unauthenticated(self):
        self.client.logout()
        url = reverse('dashboard:notifications')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
