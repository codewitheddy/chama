from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import (
    TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView,
)
from django.views import View
from django.urls import reverse_lazy, reverse
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Sum
from datetime import date

from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin, MemberAccessMixin, AdminPasswordDeleteMixin
from members.models import Member
from utils.exports import export_csv, export_pdf
from django.utils import timezone

from .models import (
    WelfareContributionRate, WelfareContribution, WelfareEvent,
    WelfareDisbursement, WelfareSupportContribution, get_welfare_balance,
    MONTH_CHOICES,
)
from .forms import (
    WelfareContributionRateForm, WelfareContributionForm, WelfareEventForm,
    WelfareDisbursementForm, WelfareSupportContributionForm,
)


# ── Dashboard ─────────────────────────────────────────────────────

class WelfareDashboardView(MemberAccessMixin, TemplateView):
    template_name = 'welfare/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['welfare_balance'] = get_welfare_balance()
        ctx['total_contributions'] = (
            WelfareContribution.objects.aggregate(t=Sum('amount'))['t'] or 0
        )
        ctx['total_disbursements'] = (
            WelfareDisbursement.objects.aggregate(t=Sum('amount'))['t'] or 0
        )
        ctx['open_events_count'] = WelfareEvent.objects.filter(status='open').count()
        ctx['recent_contributions'] = (
            WelfareContribution.objects.select_related('member').order_by('-date')[:5]
        )
        ctx['open_events'] = (
            WelfareEvent.objects.filter(status='open').select_related('beneficiary')
        )
        ctx['current_rate'] = WelfareContributionRate.current_rate()
        return ctx


# ── Contribution Rate ─────────────────────────────────────────────

class WelfareContributionRateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = WelfareContributionRate
    form_class = WelfareContributionRateForm
    template_name = 'welfare/rate_form.html'
    success_url = reverse_lazy('welfare:rate')
    success_message = "Monthly contribution rate updated."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['current_rate'] = WelfareContributionRate.current_rate()
        ctx['rate_history'] = WelfareContributionRate.objects.order_by('-effective_date')
        return ctx


# ── Welfare Contributions ─────────────────────────────────────────

class WelfareContributionListView(MemberAccessMixin, ListView):
    model = WelfareContribution
    template_name = 'welfare/contribution_list.html'
    context_object_name = 'contributions'
    paginate_by = 20

    def get_queryset(self):
        qs = WelfareContribution.objects.select_related('member').order_by('-date')
        q = self.request.GET.get('q', '').strip()
        month = self.request.GET.get('month', '').strip()
        year = self.request.GET.get('year', '').strip()
        if q:
            qs = qs.filter(member__name__icontains=q)
        if month:
            qs = qs.filter(month=month)
        if year:
            qs = qs.filter(year=year)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_month'] = self.request.GET.get('month', '')
        ctx['selected_year'] = self.request.GET.get('year', '')
        ctx['months'] = [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)]
        ctx['years'] = range(today.year - 3, today.year + 1)
        ctx['total_count'] = self.get_queryset().count()
        # Stats — always from full dataset, not filtered
        ctx['stat_total_contributions'] = (
            WelfareContribution.objects.aggregate(t=Sum('amount'))['t'] or 0
        )
        ctx['stat_total_disbursed'] = (
            WelfareDisbursement.objects.aggregate(t=Sum('amount'))['t'] or 0
        )
        ctx['stat_welfare_balance'] = get_welfare_balance()
        ctx['stat_open_events'] = WelfareEvent.objects.filter(status='open').count()
        return ctx


class WelfareContributionCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = WelfareContribution
    form_class = WelfareContributionForm
    template_name = 'welfare/contribution_form.html'
    success_url = reverse_lazy('welfare:contribution_add')
    success_message = "Welfare contribution recorded. Add another below."

    def get_initial(self):
        initial = super().get_initial()
        initial['date'] = timezone.localdate()
        rate = WelfareContributionRate.current_rate()
        if rate:
            initial['amount'] = rate.amount
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['current_rate'] = WelfareContributionRate.current_rate()
        return ctx


class WelfareContributionUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = WelfareContribution
    form_class = WelfareContributionForm
    template_name = 'welfare/contribution_form.html'
    success_url = reverse_lazy('welfare:contribution_list')
    success_message = "Welfare contribution updated."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['current_rate'] = WelfareContributionRate.current_rate()
        return ctx


class WelfareContributionDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = WelfareContribution
    template_name = 'welfare/contribution_confirm_delete.html'
    success_url = reverse_lazy('welfare:contribution_list')


class WelfareContributionExportView(TreasurerRequiredMixin, View):
    def get(self, request):
        fmt = request.GET.get('format', 'csv')
        qs = WelfareContribution.objects.select_related('member').order_by('-date')
        q = request.GET.get('q', '').strip()
        month = request.GET.get('month', '').strip()
        year = request.GET.get('year', '').strip()
        if q:
            qs = qs.filter(member__name__icontains=q)
        if month:
            qs = qs.filter(month=month)
        if year:
            qs = qs.filter(year=year)

        fields = [
            ('member.name', 'Member'),
            (lambda obj: obj.get_month_display(), 'Month'),
            ('year', 'Year'),
            ('amount', 'Amount (KES)'),
            (lambda obj: obj.get_payment_type_display(), 'Method'),
            ('mpesa_code', 'M-Pesa Code'),
            ('date', 'Date'),
        ]
        if fmt == 'pdf':
            return export_pdf(qs, 'welfare_contributions', 'Welfare Contributions', fields)
        return export_csv(qs, 'welfare_contributions', fields)


# ── Defaulters ────────────────────────────────────────────────────

class WelfareDefaultersView(MemberAccessMixin, TemplateView):
    template_name = 'welfare/defaulters.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        month = int(self.request.GET.get('month', today.month))
        year = int(self.request.GET.get('year', today.year))

        paid_ids = WelfareContribution.objects.filter(
            month=month, year=year
        ).values_list('member_id', flat=True)

        ctx['defaulters'] = Member.objects.exclude(id__in=paid_ids).order_by('name')
        ctx['month'] = month
        ctx['year'] = year
        ctx['month_name'] = date(year, month, 1).strftime('%B')
        ctx['months'] = [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)]
        ctx['years'] = range(today.year - 2, today.year + 1)
        ctx['expected_rate'] = WelfareContributionRate.rate_for_period(year, month)
        return ctx


class WelfareDefaultersExportView(TreasurerRequiredMixin, View):
    def get(self, request):
        today = timezone.localdate()
        month = int(request.GET.get('month', today.month))
        year = int(request.GET.get('year', today.year))
        month_name = date(year, month, 1).strftime('%B')

        paid_ids = WelfareContribution.objects.filter(
            month=month, year=year
        ).values_list('member_id', flat=True)

        defaulters = Member.objects.exclude(id__in=paid_ids).order_by('name')
        fields = [
            (lambda obj: obj.name, 'Member Name'),
            (lambda obj: obj.phone or '—', 'Phone'),
            (lambda obj: str(obj.date_joined), 'Date Joined'),
        ]
        title = f'Welfare Defaulters — {month_name} {year}'
        return export_pdf(defaulters, 'welfare_defaulters', title, fields)


# ── Welfare Events ────────────────────────────────────────────────

class WelfareEventListView(MemberAccessMixin, ListView):
    model = WelfareEvent
    template_name = 'welfare/event_list.html'
    context_object_name = 'events'
    paginate_by = 20

    def get_queryset(self):
        qs = WelfareEvent.objects.select_related('beneficiary').order_by('-date_opened')
        q = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        if q:
            qs = qs.filter(beneficiary__name__icontains=q)
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['current_status'] = self.request.GET.get('status', '')
        return ctx


class WelfareEventCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = WelfareEvent
    form_class = WelfareEventForm
    template_name = 'welfare/event_form.html'
    success_message = "Welfare event created."

    def get_success_url(self):
        return reverse('welfare:event_detail', kwargs={'pk': self.object.pk})


class WelfareEventUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = WelfareEvent
    form_class = WelfareEventForm
    template_name = 'welfare/event_form.html'
    success_message = "Welfare event updated."

    def get_success_url(self):
        return reverse('welfare:event_detail', kwargs={'pk': self.object.pk})


class WelfareEventDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = WelfareEvent
    template_name = 'welfare/event_confirm_delete.html'
    success_url = reverse_lazy('welfare:event_list')


class WelfareEventDetailView(MemberAccessMixin, DetailView):
    model = WelfareEvent
    template_name = 'welfare/event_detail.html'
    context_object_name = 'event'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        event = self.object
        ctx['welfare_balance'] = get_welfare_balance()
        try:
            ctx['disbursement'] = event.disbursement
        except WelfareDisbursement.DoesNotExist:
            ctx['disbursement'] = None
        ctx['support_contributions'] = (
            event.support_contributions.select_related('contributor').order_by('-date')
        )
        ctx['event_total'] = event.event_total
        return ctx


class WelfareEventCloseView(TreasurerRequiredMixin, View):
    def post(self, request, pk):
        event = get_object_or_404(WelfareEvent, pk=pk)
        event.status = 'closed'
        event.save()
        messages.success(request, f'Welfare event for {event.beneficiary.name} has been closed.')
        return redirect('welfare:event_detail', pk=pk)


# ── Disbursements ─────────────────────────────────────────────────

class WelfareDisbursementCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = WelfareDisbursement
    form_class = WelfareDisbursementForm
    template_name = 'welfare/disbursement_form.html'
    success_message = "Disbursement recorded."

    def get_event(self):
        return get_object_or_404(WelfareEvent, pk=self.kwargs['pk'])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['welfare_balance'] = get_welfare_balance()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['event'] = self.get_event()
        ctx['welfare_balance'] = get_welfare_balance()
        return ctx

    def form_valid(self, form):
        event = self.get_event()
        # Guard against duplicate disbursement
        if hasattr(event, 'disbursement'):
            messages.error(self.request, 'A disbursement has already been recorded for this event.')
            return redirect('welfare:event_detail', pk=event.pk)
        form.instance.event = event
        try:
            return super().form_valid(form)
        except IntegrityError:
            messages.error(self.request, 'A disbursement has already been recorded for this event.')
            return redirect('welfare:event_detail', pk=event.pk)

    def get_success_url(self):
        return reverse('welfare:event_detail', kwargs={'pk': self.kwargs['pk']})


class WelfareDisbursementUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = WelfareDisbursement
    form_class = WelfareDisbursementForm
    template_name = 'welfare/disbursement_form.html'
    success_message = "Disbursement updated."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['welfare_balance'] = get_welfare_balance()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['event'] = self.object.event
        ctx['welfare_balance'] = get_welfare_balance()
        return ctx

    def get_success_url(self):
        return reverse('welfare:event_detail', kwargs={'pk': self.object.event_id})


class WelfareDisbursementDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = WelfareDisbursement
    template_name = 'welfare/disbursement_confirm_delete.html'

    def get_success_url(self):
        return reverse('welfare:event_detail', kwargs={'pk': self.object.event_id})


# ── Support Contributions ─────────────────────────────────────────

class WelfareSupportCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = WelfareSupportContribution
    form_class = WelfareSupportContributionForm
    template_name = 'welfare/support_contribution_form.html'
    success_message = "Support contribution recorded."

    def get_event(self):
        return get_object_or_404(WelfareEvent, pk=self.kwargs['pk'])

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.get_event()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['event'] = self.get_event()
        return ctx

    def form_valid(self, form):
        form.instance.event = self.get_event()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('welfare:event_detail', kwargs={'pk': self.kwargs['pk']})


class WelfareSupportUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = WelfareSupportContribution
    form_class = WelfareSupportContributionForm
    template_name = 'welfare/support_contribution_form.html'
    success_message = "Support contribution updated."

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['event'] = self.object.event
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['event'] = self.object.event
        return ctx

    def get_success_url(self):
        return reverse('welfare:event_detail', kwargs={'pk': self.object.event_id})


class WelfareSupportDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = WelfareSupportContribution
    template_name = 'welfare/support_contribution_confirm_delete.html'

    def get_success_url(self):
        return reverse('welfare:event_detail', kwargs={'pk': self.object.event_id})


# ── Event PDF Export ──────────────────────────────────────────────

class WelfareEventExportView(TreasurerRequiredMixin, View):
    def get(self, request, pk):
        event = get_object_or_404(
            WelfareEvent.objects.select_related('beneficiary').prefetch_related(
                'support_contributions__contributor'
            ),
            pk=pk,
        )
        try:
            disbursement = event.disbursement
        except WelfareDisbursement.DoesNotExist:
            disbursement = None

        support_qs = event.support_contributions.select_related('contributor').order_by('-date')

        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm, mm
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_RIGHT
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
        )
        from django.http import HttpResponse
        from datetime import date as dt

        PRIMARY = colors.HexColor('#1e3a5f')
        ACCENT = colors.HexColor('#2563eb')
        GREEN = colors.HexColor('#16a34a')
        RED = colors.HexColor('#e11d48')
        ALT_ROW = colors.HexColor('#f8fafc')
        BORDER = colors.HexColor('#e2e8f0')
        TEXT_DARK = colors.HexColor('#1e293b')
        TEXT_MUTED = colors.HexColor('#64748b')
        WHITE = colors.white

        response = HttpResponse(content_type='application/pdf')
        safe_name = event.beneficiary.name.replace(' ', '_')
        response['Content-Disposition'] = f'attachment; filename="welfare_event_{event.pk}_{safe_name}.pdf"'
        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            topMargin=34*mm, bottomMargin=18*mm,
            leftMargin=1.5*cm, rightMargin=1.5*cm,
        )
        styles = getSampleStyleSheet()
        usable = A4[0] - 3*cm

        def on_page(canvas, d):
            canvas.saveState()
            w, h = A4
            canvas.setFillColor(PRIMARY)
            canvas.rect(0, h - 28*mm, w, 28*mm, fill=1, stroke=0)
            canvas.setFillColor(WHITE)
            canvas.setFont('Helvetica-Bold', 13)
            canvas.drawString(1.5*cm, h - 13*mm, 'DC Welfare Group')
            canvas.setFont('Helvetica', 8)
            canvas.drawString(1.5*cm, h - 20*mm, 'Welfare Event Summary')
            canvas.setFont('Helvetica', 9)
            canvas.drawRightString(w - 1.5*cm, h - 14*mm, event.beneficiary.name)
            canvas.setFont('Helvetica', 8)
            canvas.drawRightString(w - 1.5*cm, h - 21*mm,
                                   f'Generated: {dt.today().strftime("%d %B %Y")}')
            canvas.setFillColor(BORDER)
            canvas.rect(0, 0, w, 10*mm, fill=1, stroke=0)
            canvas.setFillColor(TEXT_MUTED)
            canvas.setFont('Helvetica', 8)
            canvas.drawString(1.5*cm, 3.5*mm, 'DC Welfare Group — Confidential')
            canvas.drawRightString(w - 1.5*cm, 3.5*mm, f'Page {d.page}')
            canvas.restoreState()

        def ps(name, **kw):
            return ParagraphStyle(name, parent=styles['Normal'], **kw)

        title_s = ps('t', fontSize=16, fontName='Helvetica-Bold', textColor=PRIMARY, spaceAfter=2*mm)
        sub_s = ps('s', fontSize=9, fontName='Helvetica', textColor=TEXT_MUTED, spaceAfter=1*mm)
        section_s = ps('sec', fontSize=10, fontName='Helvetica-Bold', textColor=PRIMARY,
                        spaceBefore=5*mm, spaceAfter=2*mm)
        cell_s = ps('c', fontSize=9, fontName='Helvetica', textColor=TEXT_DARK, leading=13)
        hdr_s = ps('h', fontSize=9, fontName='Helvetica-Bold', textColor=WHITE, leading=13)
        hdr_r = ps('hr', fontSize=9, fontName='Helvetica-Bold', textColor=WHITE,
                   leading=13, alignment=TA_RIGHT)
        green_r = ps('gr', fontSize=9, fontName='Helvetica', textColor=GREEN,
                     leading=13, alignment=TA_RIGHT)
        bold_s = ps('b', fontSize=9, fontName='Helvetica-Bold', textColor=TEXT_DARK, leading=13)
        muted_s = ps('m', fontSize=9, fontName='Helvetica', textColor=TEXT_MUTED, leading=13)

        def kes(val):
            return Paragraph(f'KES {val:,.2f}', green_r)

        def make_table(data, col_ratios):
            widths = [usable * r for r in col_ratios]
            t = Table(data, colWidths=widths, repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, ALT_ROW]),
                ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
                ('LINEBELOW', (0, 0), (-1, 0), 1.5, ACCENT),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            return t

        elements = [
            Paragraph(f'Welfare Event — {event.beneficiary.name}', title_s),
            Paragraph(f'Date: {event.date_opened}  |  Status: {event.get_status_display()}', sub_s),
            Paragraph(f'Description: {event.description}', sub_s),
            HRFlowable(width='100%', thickness=1.5, color=ACCENT, spaceBefore=3*mm, spaceAfter=4*mm),
        ]

        # Fund disbursement
        elements.append(Paragraph('Fund Disbursement', section_s))
        if disbursement:
            disb_data = [
                [Paragraph('<b>DATE</b>', hdr_s), Paragraph('<b>AMOUNT</b>', hdr_r),
                 Paragraph('<b>NOTES</b>', hdr_s)],
                [Paragraph(str(disbursement.date), cell_s),
                 kes(disbursement.amount),
                 Paragraph(disbursement.notes or '—', muted_s)],
            ]
            elements.append(make_table(disb_data, [0.25, 0.25, 0.50]))
        else:
            elements.append(Paragraph('No disbursement from the welfare fund.', muted_s))

        # Member support contributions
        elements.append(Paragraph('Member Support Contributions', section_s))
        if support_qs.exists():
            sup_data = [
                [Paragraph('<b>CONTRIBUTOR</b>', hdr_s), Paragraph('<b>AMOUNT</b>', hdr_r),
                 Paragraph('<b>DATE</b>', hdr_s)],
            ]
            for sc in support_qs:
                sup_data.append([
                    Paragraph(sc.contributor.name, cell_s),
                    kes(sc.amount),
                    Paragraph(str(sc.date), cell_s),
                ])
            elements.append(make_table(sup_data, [0.45, 0.30, 0.25]))
        else:
            elements.append(Paragraph('No member support contributions recorded.', muted_s))

        # Event total
        elements.append(Spacer(1, 6*mm))
        total_data = [
            [Paragraph('<b>SOURCE</b>', hdr_s), Paragraph('<b>AMOUNT</b>', hdr_r)],
            [Paragraph('Welfare Fund Disbursement', cell_s),
             kes(event.disbursement_amount)],
            [Paragraph('Member Support Contributions', cell_s),
             kes(event.support_total)],
            [Paragraph('<b>Total Received</b>', bold_s),
             kes(event.event_total)],
        ]
        total_tbl = Table(total_data, colWidths=[usable * 0.65, usable * 0.35], repeatRows=1)
        total_tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0fdf4')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [WHITE, ALT_ROW]),
            ('GRID', (0, 0), (-1, -1), 0.4, BORDER),
            ('LINEBELOW', (0, 0), (-1, 0), 1.5, ACCENT),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, GREEN),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(Paragraph('Event Summary', section_s))
        elements.append(total_tbl)

        doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
        response.write(buffer.getvalue())
        buffer.close()
        return response
