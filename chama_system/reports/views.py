from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView
from django.views import View
from django.http import HttpResponse
from django.db.models import Sum
import csv
from members.models import Member
from contributions.models import Contribution
from loans.models import Loan
from payments.models import Payment
from penalties.models import Penalty
from utils.exports import export_csv, export_pdf
from accounts.mixins import TreasurerRequiredMixin, MemberAccessMixin


class IncomeReportView(TreasurerRequiredMixin, TemplateView):
    template_name = 'reports/income_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from django.db.models import F, ExpressionWrapper, DecimalField
        ctx['total_reg_fees'] = Member.objects.aggregate(t=Sum('registration_fee'))['t'] or 0
        ctx['total_contributions'] = Contribution.objects.aggregate(t=Sum('amount'))['t'] or 0
        ctx['total_loans_given'] = Loan.objects.aggregate(t=Sum('loan_amount'))['t'] or 0
        # Interest collected using interest-first allocation:
        # payments cover interest+penalties before principal.
        # Per loan: min(amount_paid, total_payable - loan_amount)
        ctx['total_interest'] = sum(
            min(l.amount_paid, l.total_payable - l.loan_amount)
            for l in Loan.objects.all()
        )
        ctx['total_penalties'] = Penalty.objects.filter(paid=True).aggregate(t=Sum('amount'))['t'] or 0
        ctx['total_income'] = (ctx['total_reg_fees'] + ctx['total_contributions']
                               + ctx['total_interest'] + ctx['total_penalties'])
        return ctx


class ContributionReportView(TreasurerRequiredMixin, ListView):
    model = Contribution
    template_name = 'reports/contribution_report.html'
    context_object_name = 'contributions'
    paginate_by = 25

    def get_queryset(self):
        qs = Contribution.objects.select_related('member').order_by('-year', '-month', '-date')
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
        from datetime import date as _date
        from django.utils import timezone
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_month'] = self.request.GET.get('month', '')
        ctx['selected_year'] = self.request.GET.get('year', '')
        ctx['months'] = [(i, _date(2000, i, 1).strftime('%B')) for i in range(1, 13)]
        ctx['years'] = range(today.year - 3, today.year + 1)
        ctx['total_count'] = self.get_queryset().count()
        return ctx


class LoanReportView(TreasurerRequiredMixin, TemplateView):
    template_name = 'reports/loan_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from decimal import Decimal
        loans = list(Loan.objects.select_related('member').all())
        ctx['loans'] = loans
        ctx['total_issued'] = Loan.objects.aggregate(t=Sum('loan_amount'))['t'] or 0
        ctx['total_paid'] = Loan.objects.aggregate(t=Sum('amount_paid'))['t'] or 0
        ctx['total_balance'] = sum(l.balance for l in loans)
        # Breakdown for active/late loans only
        active_loans = [l for l in loans if l.status in ('active', 'late')]
        ctx['outstanding_principal'] = sum(
            max(l.loan_amount - l.amount_paid, Decimal('0')) for l in active_loans
        )
        ctx['outstanding_interest'] = sum(
            max(min(l.interest_amount, l.total_payable - l.amount_paid), Decimal('0'))
            for l in active_loans
        )
        return ctx


class MemberStatementView(TreasurerRequiredMixin, TemplateView):
    template_name = 'reports/member_statement.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        member_id = self.request.GET.get('member')
        ctx['members'] = Member.objects.all()
        if member_id:
            try:
                from loans.models import LoanGuarantor
                member = Member.objects.get(pk=member_id)
                ctx['selected_member'] = member
                ctx['contributions'] = member.contribution_set.all()
                ctx['loans'] = member.loan_set.all()
                ctx['payments'] = member.payment_set.all()
                ctx['guarantees'] = LoanGuarantor.objects.filter(
                    guarantor=member
                ).select_related('loan__member')
            except Member.DoesNotExist:
                pass
        return ctx


# ── CSV exports (legacy) ──────────────────────────────────────────

class ExportContributionsCSV(TreasurerRequiredMixin, View):
    def get(self, request):
        fields = [
            ('member.name', 'Member'),
            (lambda obj: obj.get_month_display(), 'Month'),
            ('year', 'Year'),
            ('amount', 'Amount (KES)'),
            ('date', 'Date'),
        ]
        return export_csv(Contribution.objects.select_related('member').all(), 'contributions', fields)


class ExportLoansCSV(TreasurerRequiredMixin, View):
    def get(self, request):
        fields = [
            ('member.name', 'Member'),
            ('loan_amount', 'Loan Amount'),
            ('duration_months', 'Duration (mo)'),
            ('interest_amount', 'Interest'),
            ('total_payable', 'Total Payable'),
            ('amount_paid', 'Paid'),
            (lambda l: str(l.balance), 'Balance'),
            ('status', 'Status'),
            ('date_taken', 'Date Taken'),
            ('due_date', 'Due Date'),
        ]
        return export_csv(Loan.objects.select_related('member').all(), 'loans', fields)


class ExportPaymentsCSV(TreasurerRequiredMixin, View):
    def get(self, request):
        fields = [
            ('member.name', 'Member'),
            ('loan.loan_amount', 'Loan Amount'),
            ('amount', 'Payment'),
            ('date', 'Date'),
            ('notes', 'Notes'),
        ]
        return export_csv(Payment.objects.select_related('member', 'loan').all(), 'payments', fields)


class ExportMembersCSV(TreasurerRequiredMixin, View):
    def get(self, request):
        fields = [
            ('name', 'Name'),
            ('phone', 'Phone'),
            ('registration_fee', 'Reg. Fee'),
            ('date_joined', 'Date Joined'),
            (lambda m: str(m.total_contributions()), 'Total Contributions'),
            (lambda m: str(m.total_loans()), 'Total Loans'),
            (lambda m: str(m.total_loan_balance()), 'Loan Balance'),
        ]
        return export_csv(Member.objects.all(), 'members', fields)


class ExportMemberStatementCSV(TreasurerRequiredMixin, View):
    def get(self, request):
        member_id = request.GET.get('member')
        if not member_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest('No member selected.')
        try:
            member = Member.objects.get(pk=member_id)
        except Member.DoesNotExist:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest('Member not found.')

        import csv
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="statement_{member.name}.csv"'
        w = csv.writer(response)

        w.writerow([f'Member Statement — {member.name}'])
        w.writerow([f'Phone: {member.phone}', f'Joined: {member.date_joined}',
                    f'Reg. Fee: KES {member.registration_fee}'])
        w.writerow([])

        w.writerow(['CONTRIBUTIONS'])
        w.writerow(['Month', 'Year', 'Amount (KES)', 'Date'])
        for c in member.contribution_set.all():
            w.writerow([c.get_month_display(), c.year, c.amount, c.date])
        w.writerow(['Total', '', member.total_contributions(), ''])
        w.writerow([])

        w.writerow(['LOANS'])
        w.writerow(['Principal', 'Interest', 'Total', 'Paid', 'Balance', 'Status', 'Due Date'])
        for l in member.loan_set.all():
            w.writerow([l.loan_amount, l.interest_amount, l.total_payable,
                        l.amount_paid, l.balance, l.status, l.due_date or ''])
        w.writerow([])

        w.writerow(['LOAN PAYMENTS'])
        w.writerow(['Loan Amount', 'Payment', 'Date', 'Notes'])
        for p in member.payment_set.all():
            w.writerow([p.loan.loan_amount, p.amount, p.date, p.notes or ''])
        w.writerow([])

        w.writerow(['PENALTIES'])
        w.writerow(['Date', 'Reason', 'Amount (KES)', 'Paid', 'Paid Date'])
        for p in member.penalties.all():
            w.writerow([p.date, p.reason, p.amount, 'Yes' if p.paid else 'No', p.paid_date or ''])

        return response


class ExportMemberStatementPDF(TreasurerRequiredMixin, View):
    def get(self, request):
        member_id = request.GET.get('member')
        if not member_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest('No member selected.')
        try:
            member = Member.objects.get(pk=member_id)
        except Member.DoesNotExist:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest('Member not found.')

        from io import BytesIO
        from datetime import date as dt
        from decimal import Decimal
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm, mm
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                        Paragraph, Spacer, HRFlowable, KeepTogether)
        from django.db.models import Sum

        PRIMARY    = colors.HexColor('#1e3a5f')
        ACCENT     = colors.HexColor('#2563eb')
        GREEN      = colors.HexColor('#16a34a')
        AMBER      = colors.HexColor('#d97706')
        RED        = colors.HexColor('#e11d48')
        ALT_ROW    = colors.HexColor('#f8fafc')
        BORDER     = colors.HexColor('#e2e8f0')
        HEADER_BG  = colors.HexColor('#f1f5f9')
        TEXT_DARK  = colors.HexColor('#1e293b')
        TEXT_MUTED = colors.HexColor('#64748b')
        WHITE      = colors.white

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="statement_{member.name}.pdf"'
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
            canvas.drawString(1.5*cm, h - 20*mm, 'Member Statement')
            canvas.setFont('Helvetica', 9)
            canvas.drawRightString(w - 1.5*cm, h - 14*mm, member.name)
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

        title_s   = ps('title',  fontSize=18, fontName='Helvetica-Bold', textColor=PRIMARY, spaceAfter=1*mm)
        sub_s     = ps('sub',    fontSize=9,  fontName='Helvetica', textColor=TEXT_MUTED, spaceAfter=1*mm)
        section_s = ps('sec',    fontSize=10, fontName='Helvetica-Bold', textColor=PRIMARY, spaceBefore=5*mm, spaceAfter=2*mm)
        cell_s    = ps('cell',   fontSize=9,  fontName='Helvetica', textColor=TEXT_DARK, leading=13)
        cell_r    = ps('cellr',  fontSize=9,  fontName='Helvetica', textColor=TEXT_DARK, leading=13, alignment=TA_RIGHT)
        hdr_s     = ps('hdr',    fontSize=9,  fontName='Helvetica-Bold', textColor=WHITE, leading=13)
        hdr_r     = ps('hdrr',   fontSize=9,  fontName='Helvetica-Bold', textColor=WHITE, leading=13, alignment=TA_RIGHT)
        bold_s    = ps('bold',   fontSize=9,  fontName='Helvetica-Bold', textColor=TEXT_DARK, leading=13)
        muted_s   = ps('muted',  fontSize=9,  fontName='Helvetica', textColor=TEXT_MUTED, leading=13)
        green_s   = ps('green',  fontSize=9,  fontName='Helvetica', textColor=GREEN, leading=13, alignment=TA_RIGHT)
        red_s     = ps('red',    fontSize=9,  fontName='Helvetica', textColor=RED, leading=13, alignment=TA_RIGHT)
        blue_s    = ps('blue',   fontSize=9,  fontName='Helvetica', textColor=ACCENT, leading=13, alignment=TA_RIGHT)
        amber_s   = ps('amber',  fontSize=9,  fontName='Helvetica-Bold', textColor=AMBER, leading=13)

        def kes(val, style=None):
            return Paragraph(f'KES {val:,.2f}', style or cell_r)

        def make_table(data, col_ratios, extra_styles=None):
            widths = [usable * r for r in col_ratios]
            t = Table(data, colWidths=widths, repeatRows=1)
            cmds = [
                ('BACKGROUND',     (0, 0), (-1, 0),  PRIMARY),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, ALT_ROW]),
                ('GRID',           (0, 0), (-1, -1), 0.4, BORDER),
                ('LINEBELOW',      (0, 0), (-1, 0),  1.5, ACCENT),
                # Header row — more vertical padding for prominence
                ('TOPPADDING',     (0, 0), (-1, 0),  10),
                ('BOTTOMPADDING',  (0, 0), (-1, 0),  10),
                ('LEFTPADDING',    (0, 0), (-1, 0),  10),
                ('RIGHTPADDING',   (0, 0), (-1, 0),  10),
                # Data rows — generous padding for readability
                ('TOPPADDING',     (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING',  (0, 1), (-1, -1), 9),
                ('LEFTPADDING',    (0, 1), (-1, -1), 10),
                ('RIGHTPADDING',   (0, 1), (-1, -1), 10),
                ('VALIGN',         (0, 0), (-1, -1), 'MIDDLE'),
            ]
            if extra_styles:
                cmds.extend(extra_styles)
            t.setStyle(TableStyle(cmds))
            return t

        # ── Aggregate data ────────────────────────────────────────
        total_pen_issued = member.penalties.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        total_pen_paid   = member.penalties.filter(paid=True).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        total_pen_unpaid = total_pen_issued - total_pen_paid
        guarantees       = member.guarantees.select_related('loan__member').all()

        elements = []

        # ── Profile card + Financial Summary (two-column) ─────────
        profile_rows = [
            [Paragraph(member.name, title_s)],
            [Paragraph(f'Phone: {member.phone or "—"}', sub_s)],
            [Paragraph(f'Joined: {member.date_joined}', sub_s)],
            [Paragraph(f'Reg. Fee: KES {member.registration_fee:,.2f}', sub_s)],
        ]
        profile_tbl = Table(profile_rows, colWidths=[usable * 0.44])
        profile_tbl.setStyle(TableStyle([
            ('TOPPADDING',    (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ]))

        fin_rows = [
            [Paragraph('<b>Financial Summary</b>', bold_s), Paragraph('')],
            [Paragraph('Total Contributions', muted_s), kes(member.total_contributions(), green_s)],
            [Paragraph('Total Loans', muted_s),         kes(member.total_loans(), blue_s)],
            [Paragraph('Loan Balance', muted_s),        kes(member.total_loan_balance(), red_s)],
            [Paragraph('Penalties Issued', muted_s),    kes(total_pen_issued, red_s)],
            [Paragraph('Penalties Paid', muted_s),      kes(total_pen_paid, green_s)],
            [Paragraph('Penalties Outstanding', muted_s), kes(total_pen_unpaid, red_s)],
        ]
        fin_tbl = Table(fin_rows, colWidths=[usable * 0.30, usable * 0.26])
        fin_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  HEADER_BG),
            ('SPAN',          (0, 0), (-1, 0)),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [WHITE, ALT_ROW]),
            ('GRID',          (0, 0), (-1, -1), 0.4, BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING',   (0, 0), (-1, -1), 12),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 12),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        header_row = Table([[profile_tbl, fin_tbl]], colWidths=[usable * 0.44, usable * 0.56])
        header_row.setStyle(TableStyle([
            ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING',  (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING',   (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 0),
        ]))
        elements.append(header_row)
        elements.append(HRFlowable(width='100%', thickness=1.5, color=ACCENT,
                                   spaceBefore=4*mm, spaceAfter=3*mm))

        # ── Contributions ─────────────────────────────────────────
        contrib_data = [[Paragraph('<b>MONTH</b>', hdr_s), Paragraph('<b>YEAR</b>', hdr_s),
                         Paragraph('<b>AMOUNT</b>', hdr_r), Paragraph('<b>DATE</b>', hdr_s)]]
        for c in member.contribution_set.all():
            contrib_data.append([
                Paragraph(c.get_month_display(), cell_s),
                Paragraph(str(c.year), cell_s),
                kes(c.amount, green_s),
                Paragraph(str(c.date), cell_s),
            ])
        if len(contrib_data) == 1:
            contrib_data.append([Paragraph('No contributions recorded.', muted_s),
                                  Paragraph(''), Paragraph(''), Paragraph('')])
        elements.append(KeepTogether([
            Paragraph('Contributions', section_s),
            make_table(contrib_data, [0.30, 0.15, 0.25, 0.30]),
        ]))

        # ── Penalties ─────────────────────────────────────────────
        pen_data = [[Paragraph('<b>DATE</b>', hdr_s), Paragraph('<b>REASON</b>', hdr_s),
                     Paragraph('<b>AMOUNT</b>', hdr_r), Paragraph('<b>STATUS</b>', hdr_s)]]
        for p in member.penalties.all():
            pen_data.append([
                Paragraph(str(p.date), cell_s),
                Paragraph(p.reason, cell_s),
                kes(p.amount, red_s),
                Paragraph('Paid' if p.paid else 'Unpaid',
                           ps(f'ps{p.pk}', fontSize=8, fontName='Helvetica-Bold',
                              textColor=GREEN if p.paid else RED, leading=11)),
            ])
        if len(pen_data) == 1:
            pen_data.append([Paragraph('No penalties.', muted_s),
                              Paragraph(''), Paragraph(''), Paragraph('')])
        pen_data.append([Paragraph(''), Paragraph('<b>Total</b>', bold_s),
                         kes(total_pen_issued, red_s), Paragraph('')])
        pen_tbl = make_table(pen_data, [0.20, 0.42, 0.20, 0.18],
                             extra_styles=[('BACKGROUND', (0, -1), (-1, -1), HEADER_BG)])
        elements.append(KeepTogether([Paragraph('Penalties', section_s), pen_tbl]))

        # ── Loans ─────────────────────────────────────────────────
        loan_data = [[
            Paragraph('<b>AMOUNT</b>', hdr_r), Paragraph('<b>INTEREST</b>', hdr_r),
            Paragraph('<b>PENALTIES</b>', hdr_r), Paragraph('<b>TOTAL</b>', hdr_r),
            Paragraph('<b>PAID</b>', hdr_r), Paragraph('<b>BALANCE</b>', hdr_r),
            Paragraph('<b>STATUS</b>', hdr_s), Paragraph('<b>DUE DATE</b>', hdr_s),
        ]]
        for l in member.loan_set.all():
            pen_total = l.late_penalty_per_month * l.late_penalty_months
            bal_style = green_s if l.balance == 0 else red_s
            if l.status == 'cleared':
                st = Paragraph('Cleared', ps(f'lsc{l.pk}', fontSize=8, fontName='Helvetica-Bold', textColor=GREEN, leading=11))
            elif l.status == 'late':
                st = Paragraph('Late', ps(f'lsl{l.pk}', fontSize=8, fontName='Helvetica-Bold', textColor=RED, leading=11))
            else:
                st = Paragraph('Active', ps(f'lsa{l.pk}', fontSize=8, fontName='Helvetica-Bold', textColor=AMBER, leading=11))
            loan_data.append([
                kes(l.loan_amount),
                kes(l.interest_amount, green_s),
                kes(pen_total, red_s if pen_total else cell_r),
                kes(l.total_payable),
                kes(l.amount_paid, blue_s),
                kes(l.balance, bal_style),
                st,
                Paragraph(str(l.due_date or '—'), cell_s),
            ])
        if len(loan_data) == 1:
            loan_data.append([Paragraph('No loans.', muted_s)] + [Paragraph('')]*7)
        elements.append(KeepTogether([
            Paragraph('Loans', section_s),
            make_table(loan_data, [0.13, 0.12, 0.12, 0.13, 0.12, 0.12, 0.12, 0.14]),
        ]))

        # ── Loan Payments ─────────────────────────────────────────
        pay_data = [[Paragraph('<b>LOAN</b>', hdr_r), Paragraph('<b>AMOUNT</b>', hdr_r),
                     Paragraph('<b>DATE</b>', hdr_s), Paragraph('<b>NOTES</b>', hdr_s)]]
        for p in member.payment_set.select_related('loan').all():
            pay_data.append([
                kes(p.loan.loan_amount),
                kes(p.amount, blue_s),
                Paragraph(str(p.date), cell_s),
                Paragraph(p.notes or '—', muted_s),
            ])
        if len(pay_data) == 1:
            pay_data.append([Paragraph('No payments recorded.', muted_s),
                              Paragraph(''), Paragraph(''), Paragraph('')])
        elements.append(KeepTogether([
            Paragraph('Loan Payments', section_s),
            make_table(pay_data, [0.25, 0.20, 0.20, 0.35]),
        ]))

        # ── Loans Guaranteed ──────────────────────────────────────
        guar_data = [[
            Paragraph('<b>BORROWER</b>', hdr_s), Paragraph('<b>LOAN AMOUNT</b>', hdr_r),
            Paragraph('<b>GUARANTEED</b>', hdr_r), Paragraph('<b>BALANCE</b>', hdr_r),
            Paragraph('<b>STATUS</b>', hdr_s),
        ]]
        for g in guarantees:
            bal_style = green_s if g.loan.balance == 0 else red_s
            if g.loan.status == 'cleared':
                st = Paragraph('Cleared', ps(f'gsc{g.pk}', fontSize=8, fontName='Helvetica-Bold', textColor=GREEN, leading=11))
            elif g.loan.status == 'late':
                st = Paragraph('Late', ps(f'gsl{g.pk}', fontSize=8, fontName='Helvetica-Bold', textColor=RED, leading=11))
            else:
                st = Paragraph('Active', ps(f'gsa{g.pk}', fontSize=8, fontName='Helvetica-Bold', textColor=AMBER, leading=11))
            guar_data.append([
                Paragraph(g.loan.member.name, cell_s),
                kes(g.loan.loan_amount),
                kes(g.amount_guaranteed, blue_s),
                kes(g.loan.balance, bal_style),
                st,
            ])
        if len(guar_data) == 1:
            guar_data.append([Paragraph('Not guaranteeing any loans.', muted_s),
                               Paragraph(''), Paragraph(''), Paragraph(''), Paragraph('')])
        elements.append(KeepTogether([
            Paragraph('Loans Guaranteed', section_s),
            make_table(guar_data, [0.28, 0.20, 0.20, 0.18, 0.14]),
        ]))

        doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
        response.write(buffer.getvalue())
        buffer.close()
        return response


# ── PDF exports ───────────────────────────────────────────────────

class ExportContributionsPDF(TreasurerRequiredMixin, View):
    def get(self, request):
        fields = [
            ('member.name', 'Member'),
            (lambda obj: obj.get_month_display(), 'Month'),
            ('year', 'Year'),
            ('amount', 'Amount (KES)'),
            ('date', 'Date'),
        ]
        return export_pdf(
            Contribution.objects.select_related('member').all(),
            'contributions_report', 'Contributions Report', fields
        )


class ExportLoansPDF(TreasurerRequiredMixin, View):
    def get(self, request):
        fields = [
            ('member.name', 'Member'),
            ('loan_amount', 'Principal (KES)'),
            ('interest_amount', 'Interest (KES)'),
            ('total_payable', 'Total (KES)'),
            ('amount_paid', 'Paid (KES)'),
            (lambda l: f"{l.balance:,.2f}", 'Balance (KES)'),
            ('status', 'Status'),
            ('due_date', 'Due Date'),
        ]
        return export_pdf(
            Loan.objects.select_related('member').all(),
            'loans_report', 'Loans Report', fields, orientation='landscape'
        )


class ExportIncomePDF(TreasurerRequiredMixin, View):
    def get(self, request):
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm, mm
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
        from reportlab.lib.enums import TA_CENTER
        from django.http import HttpResponse
        from datetime import date as dt

        PRIMARY = colors.HexColor('#1e3a5f')
        ACCENT  = colors.HexColor('#2563eb')
        ALT_ROW = colors.HexColor('#f0f4ff')
        BORDER  = colors.HexColor('#cbd5e1')
        TEXT_DARK = colors.HexColor('#1e293b')
        TEXT_MUTED = colors.HexColor('#64748b')

        from django.db.models import F, ExpressionWrapper, DecimalField as _DecField
        total_reg = Member.objects.aggregate(t=Sum('registration_fee'))['t'] or 0
        total_contrib = Contribution.objects.aggregate(t=Sum('amount'))['t'] or 0
        total_interest = sum(
            min(l.amount_paid, l.total_payable - l.loan_amount)
            for l in Loan.objects.all()
        )
        total_penalties = Penalty.objects.filter(paid=True).aggregate(t=Sum('amount'))['t'] or 0
        total_income = total_reg + total_contrib + total_interest + total_penalties

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="income_report.pdf"'
        buffer = BytesIO()

        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                topMargin=32*mm, bottomMargin=16*mm,
                                leftMargin=1.5*cm, rightMargin=1.5*cm)
        styles = getSampleStyleSheet()

        def footer(canvas, doc):
            canvas.saveState()
            w, h = A4
            canvas.setFillColor(PRIMARY)
            canvas.rect(0, h - 28*mm, w, 28*mm, fill=1, stroke=0)
            canvas.setFillColor(colors.white)
            canvas.setFont('Helvetica-Bold', 14)
            canvas.drawString(1.5*cm, h - 14*mm, 'DC Welfare Group')
            canvas.setFont('Helvetica', 9)
            canvas.drawRightString(w - 1.5*cm, h - 14*mm, 'Income Report')
            canvas.setFillColor(BORDER)
            canvas.rect(0, 0, w, 10*mm, fill=1, stroke=0)
            canvas.setFillColor(TEXT_MUTED)
            canvas.setFont('Helvetica', 8)
            canvas.drawString(1.5*cm, 3.5*mm, f'Generated: {dt.today().strftime("%d %B %Y")}')
            canvas.drawRightString(w - 1.5*cm, 3.5*mm, f'Page {doc.page}')
            canvas.restoreState()

        title_style = ParagraphStyle('T', parent=styles['Normal'], fontSize=16,
                                     fontName='Helvetica-Bold', textColor=PRIMARY, spaceAfter=2*mm)
        sub_style = ParagraphStyle('S', parent=styles['Normal'], fontSize=9,
                                   fontName='Helvetica', textColor=TEXT_MUTED, spaceAfter=4*mm)
        cell_style = ParagraphStyle('C', parent=styles['Normal'], fontSize=10,
                                    fontName='Helvetica', textColor=TEXT_DARK)
        bold_style = ParagraphStyle('B', parent=styles['Normal'], fontSize=10,
                                    fontName='Helvetica-Bold', textColor=TEXT_DARK)

        elements = [
            Paragraph('Income Report', title_style),
            Paragraph(f'Generated on {dt.today().strftime("%d %B %Y")}', sub_style),
            HRFlowable(width='100%', thickness=1, color=ACCENT, spaceAfter=6*mm),
        ]

        rows = [
            [Paragraph('<b>Income Stream</b>', ParagraphStyle('H', parent=styles['Normal'],
                       fontSize=10, fontName='Helvetica-Bold', textColor=colors.white)),
             Paragraph('<b>Amount (KES)</b>', ParagraphStyle('H2', parent=styles['Normal'],
                       fontSize=10, fontName='Helvetica-Bold', textColor=colors.white)),
             Paragraph('<b>% of Total</b>', ParagraphStyle('H3', parent=styles['Normal'],
                       fontSize=10, fontName='Helvetica-Bold', textColor=colors.white))],
            [Paragraph('Registration Fees', cell_style),
             Paragraph(f'{total_reg:,.2f}', cell_style),
             Paragraph(f'{(total_reg/total_income*100):.1f}%' if total_income else '—', cell_style)],
            [Paragraph('Member Contributions', cell_style),
             Paragraph(f'{total_contrib:,.2f}', cell_style),
             Paragraph(f'{(total_contrib/total_income*100):.1f}%' if total_income else '—', cell_style)],
            [Paragraph('Loan Interest', cell_style),
             Paragraph(f'{total_interest:,.2f}', cell_style),
             Paragraph(f'{(total_interest/total_income*100):.1f}%' if total_income else '—', cell_style)],
            [Paragraph('Penalties (Paid)', cell_style),
             Paragraph(f'{total_penalties:,.2f}', cell_style),
             Paragraph(f'{(total_penalties/total_income*100):.1f}%' if total_income else '—', cell_style)],
            [Paragraph('<b>TOTAL INCOME</b>', bold_style),
             Paragraph(f'<b>{total_income:,.2f}</b>', bold_style),
             Paragraph('<b>100%</b>', bold_style)],
        ]

        usable = A4[0] - 3*cm
        t = Table(rows, colWidths=[usable*0.5, usable*0.3, usable*0.2])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), PRIMARY),
            ('ROWBACKGROUNDS',(0, 1), (-1, -2), [colors.white, ALT_ROW]),
            ('BACKGROUND',    (0, -1), (-1, -1), colors.HexColor('#e0f2fe')),
            ('GRID',          (0, 0), (-1, -1), 0.5, BORDER),
            ('LINEBELOW',     (0, 0), (-1, 0), 1.5, ACCENT),
            ('TOPPADDING',    (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING',   (0, 0), (-1, -1), 10),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(t)

        doc.build(elements, onFirstPage=footer, onLaterPages=footer)
        response.write(buffer.getvalue())
        buffer.close()
        return response



