import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.views import View
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from .models import Meeting, MeetingAttendance, MeetingPenalty, MeetingPenaltyRule
from .forms import MeetingForm, MeetingMinutesForm, MeetingPenaltyForm, MeetingPenaltyRuleForm
from members.models import Member
from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin


# ── Meetings ─────────────────────────────────────────────────────

class MeetingListView(LoginRequiredMixin, ListView):
    model = Meeting
    template_name = 'meetings/meeting_list.html'
    context_object_name = 'meetings'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        if q:
            qs = qs.filter(venue__icontains=q)
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        return ctx


class MeetingCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = Meeting
    form_class = MeetingForm
    template_name = 'meetings/meeting_form.html'
    success_message = "Meeting created."

    def get_success_url(self):
        return reverse_lazy('meetings:detail', kwargs={'pk': self.object.pk})


class MeetingUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Meeting
    form_class = MeetingForm
    template_name = 'meetings/meeting_form.html'
    success_message = "Meeting updated."

    def dispatch(self, request, *args, **kwargs):
        meeting = self.get_object()
        if meeting.status == 'held':
            messages.error(request, "This meeting is held — use 'Edit Minutes' to update minutes only.")
            return redirect('meetings:detail', pk=meeting.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy('meetings:detail', kwargs={'pk': self.object.pk})


class MeetingUpdateMinutesView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    """Allows editing minutes only on a held meeting."""
    model = Meeting
    form_class = MeetingMinutesForm
    template_name = 'meetings/meeting_minutes_form.html'
    success_message = "Minutes updated."

    def get_success_url(self):
        return reverse_lazy('meetings:minutes', kwargs={'pk': self.object.pk})


class MeetingMinutesView(LoginRequiredMixin, DetailView):
    """Full-page view/edit for meeting minutes."""
    model = Meeting
    template_name = 'meetings/meeting_minutes_page.html'
    context_object_name = 'meeting'


class MeetingMinutesDocxView(LoginRequiredMixin, View):
    """Download minutes as a .docx file."""
    def get(self, request, pk):
        from docx import Document
        from docx.shared import Pt, RGBColor
        from bs4 import BeautifulSoup
        from django.http import HttpResponse
        import io

        meeting = get_object_or_404(Meeting, pk=pk)
        doc = Document()

        # Title
        title = doc.add_heading(f'Meeting Minutes — {meeting.date}', 0)
        title.alignment = 1  # center

        # Meta info
        doc.add_paragraph(f'Venue: {meeting.venue or "—"}')
        doc.add_paragraph(f'Status: {meeting.get_status_display()}')
        doc.add_paragraph(f'Attendance: {meeting.attendance.count()} members')
        doc.add_paragraph('')

        # Parse HTML minutes
        if meeting.minutes:
            soup = BeautifulSoup(meeting.minutes, 'html.parser')
            for el in soup.find_all(['p', 'h1', 'h2', 'h3', 'li', 'blockquote']):
                tag = el.name
                text = el.get_text()
                if not text.strip():
                    continue
                if tag in ('h1', 'h2'):
                    doc.add_heading(text, level=1)
                elif tag == 'h3':
                    doc.add_heading(text, level=2)
                elif tag == 'li':
                    doc.add_paragraph(text, style='List Bullet')
                elif tag == 'blockquote':
                    p = doc.add_paragraph(text)
                    p.style = 'Intense Quote'
                else:
                    doc.add_paragraph(text)
        else:
            doc.add_paragraph('No minutes recorded.')

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        filename = f'minutes_{meeting.date}.docx'
        response = HttpResponse(
            buf,
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class MeetingDeleteView(AdminRequiredMixin, DeleteView):
    model = Meeting
    template_name = 'meetings/meeting_confirm_delete.html'
    success_url = reverse_lazy('meetings:list')


class MeetingDetailView(LoginRequiredMixin, DetailView):
    model = Meeting
    template_name = 'meetings/meeting_detail.html'
    context_object_name = 'meeting'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        meeting = self.object
        attendance = meeting.attendance.select_related('member').all()
        attended_ids = attendance.values_list('member_id', flat=True)
        ctx['attendance'] = attendance
        ctx['penalties'] = meeting.penalties.select_related('member', 'rule').all()
        ctx['penalty_form'] = MeetingPenaltyForm(meeting=meeting)
        ctx['rules'] = list(MeetingPenaltyRule.objects.values('id', 'name', 'default_amount'))
        ctx['all_members'] = Member.objects.all()
        ctx['unrecorded_members'] = Member.objects.exclude(pk__in=attended_ids)
        return ctx


# ── Attendance ────────────────────────────────────────────────────

class SaveAttendanceView(LoginRequiredMixin, View):
    """Bulk-save attendance for a meeting."""
    def post(self, request, pk):
        meeting = get_object_or_404(Meeting, pk=pk)
        if meeting.status == 'held':
            return JsonResponse({'ok': False, 'error': 'Meeting is held — attendance is locked.'}, status=403)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON.'}, status=400)
        for row in data:
            MeetingAttendance.objects.update_or_create(
                meeting=meeting,
                member_id=row['member_id'],
                defaults={'status': row['status']},
            )
        return JsonResponse({'ok': True})


# ── Penalties ─────────────────────────────────────────────────────

class AddMeetingPenaltyView(TreasurerRequiredMixin, View):
    def post(self, request, pk):
        meeting = get_object_or_404(Meeting, pk=pk)
        if meeting.status == 'held':
            messages.error(request, "Penalties cannot be added once a meeting is marked as held.")
            return redirect('meetings:detail', pk=pk)
        form = MeetingPenaltyForm(request.POST, meeting=meeting)
        if form.is_valid():
            mp = form.save(commit=False)
            mp.meeting = meeting
            mp.save()
            messages.success(request, f"Penalty of KES {mp.amount} recorded for {mp.member.name}.")
        else:
            for err in form.errors.values():
                messages.error(request, err.as_text())
        return redirect('meetings:detail', pk=pk)


class DeleteMeetingPenaltyView(AdminRequiredMixin, View):
    def post(self, request, pk):
        mp = get_object_or_404(MeetingPenalty, pk=pk)
        if mp.meeting.status == 'held':
            messages.error(request, "Penalties cannot be deleted once a meeting is marked as held.")
            return redirect('meetings:detail', pk=mp.meeting_id)
        meeting_pk = mp.meeting_id
        mp.delete()
        messages.success(request, "Penalty removed.")
        return redirect('meetings:detail', pk=meeting_pk)


# ── Penalty Rules ─────────────────────────────────────────────────

class PenaltyRuleListView(AdminRequiredMixin, ListView):
    model = MeetingPenaltyRule
    template_name = 'meetings/penalty_rules.html'
    context_object_name = 'rules'


class PenaltyRuleCreateView(AdminRequiredMixin, SuccessMessageMixin, CreateView):
    model = MeetingPenaltyRule
    form_class = MeetingPenaltyRuleForm
    template_name = 'meetings/penalty_rule_form.html'
    success_url = reverse_lazy('meetings:rules')
    success_message = "Penalty rule created."


class PenaltyRuleUpdateView(AdminRequiredMixin, SuccessMessageMixin, UpdateView):
    model = MeetingPenaltyRule
    form_class = MeetingPenaltyRuleForm
    template_name = 'meetings/penalty_rule_form.html'
    success_url = reverse_lazy('meetings:rules')
    success_message = "Penalty rule updated."


class PenaltyRuleDeleteView(AdminRequiredMixin, DeleteView):
    model = MeetingPenaltyRule
    template_name = 'meetings/penalty_rule_confirm_delete.html'
    success_url = reverse_lazy('meetings:rules')
