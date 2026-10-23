from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal

from members.models import Member
from meetings.models import Meeting, MeetingAttendance, MeetingPenaltyRule, MeetingPenalty
from contributions.models import Contribution
from welfare.models import WelfareContribution


class MeetingViewAndTemplateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin_meeting", password="adminpassword123")
        self.client = Client()
        self.client.force_login(self.user)

        self.member1 = Member.objects.create(name="Jane Doe", phone="+254711111111", is_active=True)
        self.member2 = Member.objects.create(name="John Smith", phone="+254722222222", is_active=True)

        today = timezone.localdate()
        Contribution.objects.create(
            member=self.member1,
            amount=Decimal('1000.00'),
            date=today,
            month=today.month,
            year=today.year,
            payment_type='cash',
        )
        WelfareContribution.objects.create(
            member=self.member1,
            amount=Decimal('200.00'),
            date=today,
            month=today.month,
            year=today.year,
            payment_type='cash',
        )

        self.meeting = Meeting.objects.create(
            date=today,
            venue="Main Hall",
            agenda="1. Welcome\n2. Financials",
            status="scheduled",
        )

    def test_meeting_list_view(self):
        url = reverse('meetings:list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_meeting_create_view_get(self):
        url = reverse('meetings:add')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('financial_summary', response.context)
        self.assertIn('form', response.context)

    def test_meeting_create_view_post(self):
        url = reverse('meetings:add')
        today = timezone.localdate()
        response = self.client.post(url, {
            'date': today.strftime('%Y-%m-%d'),
            'venue': 'Chama Plaza',
            'agenda': '1. Standard Agenda',
            'status': 'scheduled',
            'minutes': '',
        })
        self.assertEqual(response.status_code, 302)
        new_meeting = Meeting.objects.filter(venue='Chama Plaza').first()
        self.assertIsNotNone(new_meeting)
        self.assertEqual(new_meeting.attendance.count(), 2)

    def test_meeting_detail_view(self):
        url = reverse('meetings:detail', kwargs={'pk': self.meeting.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('financial_summary', response.context)

    def test_meeting_update_view_get(self):
        url = reverse('meetings:edit', kwargs={'pk': self.meeting.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('financial_summary', response.context)

    def test_meeting_minutes_view_get(self):
        url = reverse('meetings:minutes', kwargs={'pk': self.meeting.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('financial_summary', response.context)

    def test_meeting_edit_minutes_form_get(self):
        self.meeting.status = 'held'
        self.meeting.save()
        url = reverse('meetings:edit_minutes', kwargs={'pk': self.meeting.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('financial_summary', response.context)

    def test_financial_summary_api(self):
        url = reverse('meetings:financial_summary_api')
        response = self.client.get(url, {'date': self.meeting.date.strftime('%Y-%m-%d')})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('ok'))
        self.assertEqual(data['data']['cumulative_shares'], 1000.0)
        self.assertEqual(data['data']['cumulative_welfare'], 200.0)

    def test_pdf_export(self):
        url = reverse('meetings:minutes_pdf', kwargs={'pk': self.meeting.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_docx_export(self):
        url = reverse('meetings:minutes_docx', kwargs={'pk': self.meeting.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
