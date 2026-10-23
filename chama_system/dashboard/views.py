from utils.exports import _get_group_name, _get_document_footer, draw_pdf_page_chrome, _get_document_footer, draw_pdf_page_chrome
from django.contrib.auth.mixins import LoginRequiredMixin

from django.views.generic import TemplateView

from django.views import View

from django.http import HttpResponse

from django.db.models import Sum, F, ExpressionWrapper, DecimalField

from members.models import Member

from contributions.models import Contribution

from loans.models import Loan

from payments.models import Payment

from penalties.models import Penalty

from django.utils import timezone

from io import BytesIO

import json

from decimal import Decimal





class DashboardView(LoginRequiredMixin, TemplateView):

    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            ctx.update(self._build_context())
        except Exception:
            ctx.update({
                'total_members': 0, 'total_contributions': 0, 'total_reg_fees': 0,
                'total_loans_given': 0, 'total_interest_projected': 0,
                'total_interest_collected': 0, 'total_loan_balance': 0,
                'total_loan_paid': 0, 'total_income': 0, 'total_penalties': 0,
                'treasurer_balance': 0, 'available_fund_balance': 0,
                'principal_outstanding': 0, 'outstanding_interest': 0,
                'recent_contributions': [], 'recent_loans': [], 'recent_payments': [],
                'contrib_chart_data': json.dumps([0] * 12),
                'loan_chart_data': json.dumps([0] * 12),
                'chart_year': timezone.localdate().year,
                'total_other_income': 0, 'total_bank_balance': 0, 'recent_other_income': [],
            })
        return ctx

    def _build_context(self):
        today = timezone.localdate()

        total_members = Member.objects.count()
        total_contributions = Contribution.objects.aggregate(t=Sum('amount'))['t'] or 0
        total_reg_fees = Member.objects.aggregate(t=Sum('registration_fee_paid'))['t'] or 0
        total_loans_given = Loan.objects.aggregate(t=Sum('loan_amount'))['t'] or 0
        projected_qs = Loan.objects.aggregate(
            t=Sum(ExpressionWrapper(F('total_payable') - F('loan_amount'), output_field=DecimalField()))
        )
        total_interest_projected = projected_qs['t'] or 0

        loans_qs = Loan.objects.annotate(
            interest_charged=ExpressionWrapper(F('total_payable') - F('loan_amount'), output_field=DecimalField())
        )
        interest_collected_total = sum(
            min(l.amount_paid, l.interest_charged)
            for l in loans_qs.only('amount_paid', 'total_payable', 'loan_amount')
        )
        total_interest_collected = interest_collected_total

        balance_qs = Loan.objects.filter(status__in=['active', 'late']).aggregate(
            bal=Sum(ExpressionWrapper(F('total_payable') - F('amount_paid'), output_field=DecimalField()))
        )
        total_loan_balance = max(balance_qs['bal'] or 0, 0)

        total_loan_paid = Loan.objects.aggregate(t=Sum('amount_paid'))['t'] or 0
        total_penalties = Penalty.objects.filter(paid=True).aggregate(t=Sum('amount'))['t'] or 0

        # Other income — fetched here so it can be included in total_income
        try:
            from other_income.models import OtherIncome as _OI
            total_other_income = _OI.objects.aggregate(t=Sum('amount'))['t'] or 0
            recent_other_income = list(_OI.objects.order_by('-date')[:5])
        except Exception:
            total_other_income = 0
            recent_other_income = []

        # Registration fees excluded from group income (separate Registration Fee Fund)
        total_income = total_contributions + total_interest_collected + total_penalties + total_other_income

        active_loans_list = list(Loan.objects.filter(
            status__in=['active', 'late']
        ).only('loan_amount', 'amount_paid', 'interest_amount', 'total_payable'))
        principal_outstanding = sum(max(l.loan_amount - l.amount_paid, 0) for l in active_loans_list)
        outstanding_interest = sum(
            max(min(l.interest_amount, l.total_payable - l.amount_paid), 0)
            for l in active_loans_list
        )

        from utils.financials import get_available_fund_balance
        treasurer_balance = get_available_fund_balance()

        # Bank balance
        from utils.financials import get_total_bank_balance
        total_bank_balance = get_total_bank_balance()
        welfare_bank_balance = get_total_bank_balance(fund_type='welfare')

        # Investment returns and expenses
        from investments.models import InvestmentReturn, InvestmentWithdrawal
        from expenses.models import Expense
        from members.models import RegistrationFeeRate
        
        total_investment_returns = InvestmentReturn.objects.aggregate(t=Sum('amount'))['t'] or 0
        total_investment_withdrawn = InvestmentWithdrawal.objects.aggregate(t=Sum('amount_received'))['t'] or 0
        total_expenses = Expense.objects.aggregate(t=Sum('amount'))['t'] or 0
        
        # Registration fee balance = actual collected - expenses from reg fee fund
        # Use actual collected amounts (Member.registration_fee_paid) not theoretical
        total_reg_fees_collected = Member.objects.aggregate(t=Sum('registration_fee_paid'))['t'] or Decimal('0')
        reg_fee_expenses = Expense.objects.filter(fund_source='registration_fees').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        reg_fee_balance = max(total_reg_fees_collected - reg_fee_expenses, Decimal('0'))

        today_year = today.year
        contrib_by_month = (
            Contribution.objects.filter(year=today_year)
            .values('month').annotate(total=Sum('amount')).order_by('month')
        )
        contrib_chart = [0] * 12
        for row in contrib_by_month:
            contrib_chart[row['month'] - 1] = float(row['total'])

        from django.db.models.functions import ExtractMonth as _ExtractMonth
        loan_by_month = (
            Loan.objects.filter(date_taken__year=today_year)
            .annotate(month=_ExtractMonth('date_taken'))
            .values('month').annotate(total=Sum('loan_amount')).order_by('month')
        )
        loan_chart = [0] * 12
        for row in loan_by_month:
            if row['month']:
                loan_chart[row['month'] - 1] = float(row['total'])

        return {
            'total_members': total_members,
            'total_contributions': total_contributions,
            'total_reg_fees': total_reg_fees,
            'total_loans_given': total_loans_given,
            'total_interest_projected': total_interest_projected,
            'total_interest_collected': total_interest_collected,
            'total_loan_balance': total_loan_balance,
            'total_loan_paid': total_loan_paid,
            'total_income': total_income,
            'total_penalties': total_penalties,
            'treasurer_balance': treasurer_balance,
            'available_fund_balance': treasurer_balance,
            'principal_outstanding': principal_outstanding,
            'outstanding_interest': outstanding_interest,
            'recent_contributions': Contribution.objects.select_related('member').order_by('-date')[:5],
            'recent_loans': Loan.objects.select_related('member').order_by('-date_taken')[:5],
            'recent_payments': Payment.objects.select_related('member').order_by('-date')[:5],
            'contrib_chart_data': json.dumps(contrib_chart),
            'loan_chart_data': json.dumps(loan_chart),
            'chart_year': today_year,
            'total_other_income': total_other_income,
            'total_bank_balance': total_bank_balance,
            'welfare_bank_balance': welfare_bank_balance,
            'recent_other_income': recent_other_income,
            'total_investment_returns': total_investment_returns,
            'total_investment_withdrawn': total_investment_withdrawn,
            'total_expenses': total_expenses,
            'reg_fee_balance': reg_fee_balance,
        }

class NotificationsView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/notifications.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from datetime import timedelta
        from django.db.models import Sum
        from decimal import Decimal

        from contributions.models import Contribution
        from welfare.models import WelfareContribution
        from loans.models import Loan, LoanApplication
        from penalties.models import Penalty
        from meetings.models import Meeting

        today = timezone.localdate()

        # 1. Late loans
        late_loans = list(
            Loan.objects
            .filter(status='late')
            .select_related('member')
            .order_by('due_date')
        )
        late_loans_total = sum((l.balance for l in late_loans), Decimal('0.00'))

        # 2. Loans due within 7 days
        due_soon = list(
            Loan.objects
            .filter(status='active', due_date__gte=today,
                    due_date__lte=today + timedelta(days=7))
            .select_related('member')
            .order_by('due_date')
        )
        due_soon_total = sum((l.balance for l in due_soon), Decimal('0.00'))

        # 3. Pending loan applications
        pending_applications = list(
            LoanApplication.objects
            .filter(status='pending')
            .select_related('member', 'applied_by')
            .order_by('-applied_at')
        )
        pending_apps_total = sum((app.loan_amount for app in pending_applications), Decimal('0.00'))

        # 4. Unpaid penalties
        unpaid_penalties = list(
            Penalty.objects
            .filter(paid=False)
            .select_related('member')
            .order_by('-amount')
        )
        unpaid_penalties_total = sum((p.amount for p in unpaid_penalties), Decimal('0.00'))

        # 5. Members with no share contribution this month
        paid_shares_ids = Contribution.objects.filter(
            month=today.month, year=today.year
        ).values_list('member_id', flat=True)

        no_shares = list(
            Member.objects
            .filter(is_active=True)
            .exclude(id__in=paid_shares_ids)
            .order_by('name')
        )

        # 6. Members with no welfare contribution this month
        paid_welfare_ids = WelfareContribution.objects.filter(
            month=today.month, year=today.year
        ).values_list('member_id', flat=True)

        no_welfare = list(
            Member.objects
            .filter(is_active=True)
            .exclude(id__in=paid_welfare_ids)
            .order_by('name')
        )

        # 7. Upcoming scheduled meetings
        upcoming_meetings = list(
            Meeting.objects
            .filter(status='scheduled', date__gte=today)
            .order_by('date')[:5]
        )

        # Aggregated Metrics
        total_alert_count = (
            len(late_loans) +
            len(due_soon) +
            len(pending_applications) +
            len(unpaid_penalties) +
            len(no_shares)
        )
        critical_count = len(late_loans) + len(pending_applications)
        attention_count = len(due_soon) + len(unpaid_penalties)

        # 8. Monthly Compliance & Collection Progress
        total_active_members = Member.objects.filter(is_active=True).count()
        shares_paid_count = total_active_members - len(no_shares)
        welfare_paid_count = total_active_members - len(no_welfare)
        shares_compliance_pct = round((shares_paid_count / total_active_members * 100), 1) if total_active_members else 0
        welfare_compliance_pct = round((welfare_paid_count / total_active_members * 100), 1) if total_active_members else 0

        this_month_shares_collected = Contribution.objects.filter(
            month=today.month, year=today.year
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        this_month_welfare_collected = WelfareContribution.objects.filter(
            month=today.month, year=today.year
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        ctx.update({
            'late_loans':                  late_loans,
            'late_loans_total':            late_loans_total,
            'due_soon':                    due_soon,
            'due_soon_total':              due_soon_total,
            'pending_applications':        pending_applications,
            'pending_apps_total':          pending_apps_total,
            'unpaid_penalties':            unpaid_penalties,
            'unpaid_penalties_total':      unpaid_penalties_total,
            'no_shares':                   no_shares,
            'no_welfare':                  no_welfare,
            'no_contribution':             no_shares,  # backward-compatibility
            'upcoming_meetings':           upcoming_meetings,
            'total_alert_count':           total_alert_count,
            'critical_count':              critical_count,
            'attention_count':             attention_count,
            'total_active_members':        total_active_members,
            'shares_paid_count':           shares_paid_count,
            'shares_compliance_pct':       shares_compliance_pct,
            'welfare_paid_count':          welfare_paid_count,
            'welfare_compliance_pct':      welfare_compliance_pct,
            'this_month_shares_collected': this_month_shares_collected,
            'this_month_welfare_collected': this_month_welfare_collected,
            'this_month_name':             today.strftime('%B'),
            'this_year':                   today.year,
            'today':                       today,
        })
        return ctx





class DashboardExportPDFView(LoginRequiredMixin, View):

    """Export the dashboard summary as a styled PDF report."""



    def get(self, request):

        from reportlab.lib.pagesizes import A4

        from reportlab.lib import colors

        from reportlab.lib.units import cm, mm

        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        from reportlab.lib.enums import TA_RIGHT, TA_CENTER

        from reportlab.platypus import (

            SimpleDocTemplate, Table, TableStyle, Paragraph,

            Spacer, HRFlowable,

        )



        today = timezone.localdate()



        # -- Gather all the same data as DashboardView -------------

        total_members = Member.objects.count()

        active_members = Member.objects.filter(is_active=True).count()

        total_contributions = Contribution.objects.aggregate(t=Sum('amount'))['t'] or 0

        total_reg_fees = Member.objects.aggregate(t=Sum('registration_fee_paid'))['t'] or 0

        total_loans_given = Loan.objects.aggregate(t=Sum('loan_amount'))['t'] or 0



        loans_qs = Loan.objects.annotate(

            interest_charged=ExpressionWrapper(

                F('total_payable') - F('loan_amount'),

                output_field=DecimalField(),

            )

        ).only('amount_paid', 'total_payable', 'loan_amount', 'status', 'interest_amount')



        total_interest_projected = Loan.objects.aggregate(

            t=Sum(ExpressionWrapper(F('total_payable') - F('loan_amount'), output_field=DecimalField()))

        )['t'] or 0



        interest_collected = sum(min(l.amount_paid, l.interest_charged) for l in loans_qs)



        total_loan_paid = Loan.objects.aggregate(t=Sum('amount_paid'))['t'] or 0

        total_penalties = Penalty.objects.filter(paid=True).aggregate(t=Sum('amount'))['t'] or 0

        try:
            from other_income.models import OtherIncome as _OI
            total_other_income = _OI.objects.aggregate(t=Sum('amount'))['t'] or 0
        except Exception:
            total_other_income = 0

        total_income = total_contributions + interest_collected + total_penalties + total_other_income
        # Registration fees excluded from total_income (separate Registration Fee Fund)



        active_loans_list = [l for l in loans_qs if l.status in ('active', 'late')]

        principal_outstanding = sum(max(l.loan_amount - l.amount_paid, 0) for l in active_loans_list)

        outstanding_interest = sum(

            max(min(l.interest_amount, l.total_payable - l.amount_paid), 0)

            for l in active_loans_list

        )

        total_loan_balance = principal_outstanding + outstanding_interest



        active_count  = Loan.objects.filter(status='active').count()

        late_count    = Loan.objects.filter(status='late').count()

        cleared_count = Loan.objects.filter(status='cleared').count()



        from utils.financials import get_available_fund_balance

        treasurer_balance = get_available_fund_balance()



        # Month-by-month contributions this year

        contrib_by_month = (

            Contribution.objects.filter(year=today.year)

            .values('month').annotate(total=Sum('amount')).order_by('month')

        )

        month_names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

        contrib_monthly = {row['month']: float(row['total']) for row in contrib_by_month}



        # -- PDF setup ---------------------------------------------

        PRIMARY    = colors.HexColor('#1e3a5f')

        ACCENT     = colors.HexColor('#2563eb')

        SUCCESS    = colors.HexColor('#16a34a')

        AMBER      = colors.HexColor('#d97706')

        DANGER     = colors.HexColor('#e11d48')

        ALT_ROW    = colors.HexColor('#f8fafc')

        BORDER     = colors.HexColor('#cbd5e1')

        TEXT_DARK  = colors.HexColor('#1e293b')

        TEXT_MUTED = colors.HexColor('#64748b')

        GREEN_BG   = colors.HexColor('#f0fdf4')

        NAVY_BG    = colors.HexColor('#1e2a3a')



        response = HttpResponse(content_type='application/pdf')

        response['Content-Disposition'] = (

            f'attachment; filename="dashboard_summary_{today.strftime("%Y%m%d")}.pdf"'

        )



        buffer = BytesIO()

        pw, ph = A4

        doc = SimpleDocTemplate(

            buffer, pagesize=A4,

            topMargin=32*mm, bottomMargin=16*mm,

            leftMargin=1.5*cm, rightMargin=1.5*cm,

        )

        usable = pw - 3*cm

        styles = getSampleStyleSheet()



        def ps(name, **kw):

            return ParagraphStyle(name, parent=styles['Normal'], **kw)



        title_s   = ps('T',  fontSize=16, fontName='Helvetica-Bold', textColor=PRIMARY, spaceAfter=1*mm)

        sub_s     = ps('S',  fontSize=9,  fontName='Helvetica', textColor=TEXT_MUTED, spaceAfter=4*mm)

        section_s = ps('Sc', fontSize=10, fontName='Helvetica-Bold', textColor=PRIMARY,

                        spaceBefore=5*mm, spaceAfter=2*mm)

        cell_s    = ps('C',  fontSize=9,  fontName='Helvetica', textColor=TEXT_DARK, leading=13)

        cell_r    = ps('Cr', fontSize=9,  fontName='Helvetica', textColor=TEXT_DARK,

                        leading=13, alignment=TA_RIGHT)

        hdr_s     = ps('H',  fontSize=8,  fontName='Helvetica-Bold', textColor=colors.white, leading=12)

        hdr_r     = ps('Hr', fontSize=8,  fontName='Helvetica-Bold', textColor=colors.white,

                        leading=12, alignment=TA_RIGHT)

        lbl_s     = ps('L',  fontSize=8,  fontName='Helvetica', textColor=TEXT_MUTED, leading=12)

        val_s     = ps('V',  fontSize=11, fontName='Helvetica-Bold', textColor=TEXT_DARK, leading=14)

        green_v   = ps('GV', fontSize=11, fontName='Helvetica-Bold', textColor=SUCCESS, leading=14)

        amber_v   = ps('AV', fontSize=11, fontName='Helvetica-Bold', textColor=AMBER, leading=14)

        red_v     = ps('RV', fontSize=11, fontName='Helvetica-Bold', textColor=DANGER, leading=14)

        blue_v    = ps('BV', fontSize=11, fontName='Helvetica-Bold', textColor=ACCENT, leading=14)

        muted_c   = ps('Mc', fontSize=8,  fontName='Helvetica', textColor=TEXT_MUTED,

                        leading=12, alignment=TA_RIGHT)



        def page_footer(canvas, doc):
            draw_pdf_page_chrome(canvas, doc, title='Dashboard Summary', header_right_line2=f'Generated: {today.strftime("%d %B %Y")}')



        elements = []



        # -- Title -------------------------------------------------

        elements.append(Paragraph('Dashboard Summary', title_s))

        elements.append(Paragraph(

            f'As of {today.strftime("%d %B %Y")}  |  {active_members} active members',

            sub_s,

        ))

        elements.append(HRFlowable(width='100%', thickness=1, color=ACCENT, spaceAfter=4*mm))



        # -- Key metrics grid (5 rows × 2 cols) -------------------

        def stat_cell(label, value, value_style=None):

            return [Paragraph(label, lbl_s), Paragraph(value, value_style or val_s)]



        half = usable / 2 - 3*mm

        metrics = [

            [

                Table([stat_cell('Total Members', str(total_members), blue_v)],

                      colWidths=[half*0.55, half*0.45]),

                Table([stat_cell('Active Members', str(active_members), blue_v)],

                      colWidths=[half*0.55, half*0.45]),

            ],

            [

                Table([stat_cell('Total Contributions', f'KES {total_contributions:,.0f}', green_v)],

                      colWidths=[half*0.55, half*0.45]),

                Table([stat_cell('Registration Fees', f'KES {total_reg_fees:,.0f}', green_v)],

                      colWidths=[half*0.55, half*0.45]),

            ],

            [

                Table([stat_cell('Total Loans Given', f'KES {total_loans_given:,.0f}', amber_v)],

                      colWidths=[half*0.55, half*0.45]),

                Table([stat_cell('Total Loan Paid', f'KES {total_loan_paid:,.0f}', green_v)],

                      colWidths=[half*0.55, half*0.45]),

            ],

            [

                Table([stat_cell('Interest Collected', f'KES {interest_collected:,.0f}', green_v)],

                      colWidths=[half*0.55, half*0.45]),

                Table([stat_cell('Penalties Collected', f'KES {total_penalties:,.0f}', green_v)],

                      colWidths=[half*0.55, half*0.45]),

            ],

            [

                Table([stat_cell('Outstanding Balance', f'KES {total_loan_balance:,.0f}', red_v)],

                      colWidths=[half*0.55, half*0.45]),

                Table([stat_cell('Total Income', f'KES {total_income:,.0f}', blue_v)],

                      colWidths=[half*0.55, half*0.45]),

            ],

        ]

        for inner in metrics:

            for t in inner:

                t.setStyle(TableStyle([

                    ('BACKGROUND',    (0, 0), (-1, -1), ALT_ROW),

                    ('GRID',          (0, 0), (-1, -1), 0.4, BORDER),

                    ('TOPPADDING',    (0, 0), (-1, -1), 8),

                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),

                    ('LEFTPADDING',   (0, 0), (-1, -1), 10),

                    ('RIGHTPADDING',  (0, 0), (-1, -1), 6),

                    ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),

                ]))



        grid = Table(metrics, colWidths=[half + 3*mm, half + 3*mm], hAlign='LEFT')

        grid.setStyle(TableStyle([

            ('LEFTPADDING',  (0, 0), (-1, -1), 3),

            ('RIGHTPADDING', (0, 0), (-1, -1), 3),

            ('TOPPADDING',   (0, 0), (-1, -1), 3),

            ('BOTTOMPADDING',(0, 0), (-1, -1), 3),

        ]))

        elements.append(grid)



        # -- Treasurer Balance highlight ---------------------------

        elements.append(Spacer(1, 4*mm))

        tb_data = [[

            Paragraph('TREASURER BALANCE', ps('tbl', fontSize=9, fontName='Helvetica-Bold',

                       textColor=colors.HexColor('#4ade80'), leading=12)),

            Paragraph(f'KES {treasurer_balance:,.2f}',

                      ps('tbv', fontSize=18, fontName='Helvetica-Bold',

                         textColor=colors.white, leading=22, alignment=TA_RIGHT)),

        ], [

            Paragraph(

                f'Income: KES {total_income:,.0f}  |  '

                f'Contributions: KES {float(total_contributions):,.0f}  |  '

                f'Interest: KES {interest_collected:,.0f}  |  '

                f'Penalties: KES {total_penalties:,.0f}',

                ps('tbs', fontSize=8, fontName='Helvetica',

                   textColor=colors.HexColor('#94a3b8'), leading=11)

            ),

            Paragraph('', lbl_s),

        ]]

        tb_tbl = Table(tb_data, colWidths=[usable * 0.45, usable * 0.55])

        tb_tbl.setStyle(TableStyle([

            ('BACKGROUND',    (0, 0), (-1, -1), NAVY_BG),

            ('SPAN',          (0, 1), (-1, 1)),

            ('TOPPADDING',    (0, 0), (-1, -1), 10),

            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),

            ('LEFTPADDING',   (0, 0), (-1, -1), 14),

            ('RIGHTPADDING',  (0, 0), (-1, -1), 14),

            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),

        ]))

        elements.append(tb_tbl)



        # -- Loan portfolio + Monthly contributions side by side ---

        # Loan portfolio

        elements.append(Paragraph('Loan Portfolio', section_s))

        loan_data = [

            [Paragraph('STATUS', hdr_s), Paragraph('COUNT', hdr_r),

             Paragraph('OUTSTANDING (KES)', hdr_r)],

            [Paragraph('Active', cell_s),

             Paragraph(str(active_count), cell_r),

             Paragraph(f'{principal_outstanding:,.2f}', cell_r)],

            [Paragraph('Late', ps('late', fontSize=9, fontName='Helvetica-Bold',

                                   textColor=DANGER, leading=13)),

             Paragraph(str(late_count), cell_r),

             Paragraph(f'{outstanding_interest:,.2f}', cell_r)],

            [Paragraph('Cleared', ps('cl', fontSize=9, fontName='Helvetica',

                                      textColor=SUCCESS, leading=13)),

             Paragraph(str(cleared_count), cell_r),

             Paragraph('', muted_c)],

            [Paragraph('Total Balance', ps('tot', fontSize=9, fontName='Helvetica-Bold',

                                            textColor=TEXT_DARK, leading=13)),

             Paragraph(str(active_count + late_count + cleared_count), cell_r),

             Paragraph(f'KES {total_loan_balance:,.2f}',

                       ps('totv', fontSize=9, fontName='Helvetica-Bold',

                           textColor=DANGER, leading=13, alignment=TA_RIGHT))],

        ]

        loan_tbl = Table(loan_data, colWidths=[usable*0.40, usable*0.25, usable*0.35], repeatRows=1)

        loan_tbl.setStyle(TableStyle([

            ('BACKGROUND',    (0, 0), (-1, 0), PRIMARY),

            ('ROWBACKGROUNDS',(0, 1), (-1, -2), [colors.white, ALT_ROW]),

            ('BACKGROUND',    (0, -1), (-1, -1), colors.HexColor('#fff1f2')),

            ('GRID',          (0, 0), (-1, -1), 0.4, BORDER),

            ('LINEBELOW',     (0, 0), (-1, 0), 1.5, ACCENT),

            ('LINEABOVE',     (0, -1), (-1, -1), 1, DANGER),

            ('TOPPADDING',    (0, 0), (-1, -1), 7),

            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),

            ('LEFTPADDING',   (0, 0), (-1, -1), 10),

            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),

            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),

        ]))

        elements.append(loan_tbl)



        # Monthly contributions

        elements.append(Paragraph(f'Contributions by Month  {today.year}', section_s))

        month_rows = [[

            Paragraph('MONTH', hdr_s),

            Paragraph('AMOUNT (KES)', hdr_r),

        ]]

        for i, name in enumerate(month_names, 1):

            amt = contrib_monthly.get(i, 0)

            month_rows.append([

                Paragraph(name, cell_s),

                Paragraph(f'{amt:,.2f}' if amt else '', cell_r if amt else muted_c),

            ])

        total_this_year = sum(contrib_monthly.values())

        month_rows.append([

            Paragraph('Total', ps('mt', fontSize=9, fontName='Helvetica-Bold',

                                   textColor=TEXT_DARK, leading=13)),

            Paragraph(f'KES {total_this_year:,.2f}',

                      ps('mv', fontSize=9, fontName='Helvetica-Bold',

                          textColor=SUCCESS, leading=13, alignment=TA_RIGHT)),

        ])

        month_tbl = Table(month_rows, colWidths=[usable*0.4, usable*0.6], repeatRows=1)

        month_tbl.setStyle(TableStyle([

            ('BACKGROUND',    (0, 0),  (-1, 0),  PRIMARY),

            ('ROWBACKGROUNDS',(0, 1),  (-1, -2), [colors.white, ALT_ROW]),

            ('BACKGROUND',    (0, -1), (-1, -1), GREEN_BG),

            ('GRID',          (0, 0),  (-1, -1), 0.4, BORDER),

            ('LINEBELOW',     (0, 0),  (-1, 0),  1.5, ACCENT),

            ('LINEABOVE',     (0, -1), (-1, -1), 1, SUCCESS),

            ('TOPPADDING',    (0, 0),  (-1, -1), 6),

            ('BOTTOMPADDING', (0, 0),  (-1, -1), 6),

            ('LEFTPADDING',   (0, 0),  (-1, -1), 10),

            ('RIGHTPADDING',  (0, 0),  (-1, -1), 10),

            ('VALIGN',        (0, 0),  (-1, -1), 'MIDDLE'),

        ]))

        elements.append(month_tbl)



        # -- Build -------------------------------------------------

        doc.build(elements, onFirstPage=page_footer, onLaterPages=page_footer)

        pdf = buffer.getvalue()

        buffer.close()

        response.write(pdf)

        return response

        PRIMARY    = colors.HexColor('#1e3a5f')

        ACCENT     = colors.HexColor('#2563eb')

        SUCCESS    = colors.HexColor('#16a34a')

        AMBER      = colors.HexColor('#d97706')

        DANGER     = colors.HexColor('#e11d48')

        ALT_ROW    = colors.HexColor('#f8fafc')

        BORDER     = colors.HexColor('#cbd5e1')

        TEXT_DARK  = colors.HexColor('#1e293b')

        TEXT_MUTED = colors.HexColor('#64748b')

        GREEN_BG   = colors.HexColor('#f0fdf4')

        NAVY_BG    = colors.HexColor('#1e2a3a')



        title_str = f'Dashboard Summary  {today.strftime("%d %B %Y")}'

        response = HttpResponse(content_type='application/pdf')

        response['Content-Disposition'] = (

            f'attachment; filename="dashboard_summary_{today.strftime("%Y%m%d")}.pdf"'

        )



        buffer = BytesIO()

        pw, ph = A4

        doc = SimpleDocTemplate(

            buffer, pagesize=A4,

            topMargin=32*mm, bottomMargin=16*mm,

            leftMargin=1.5*cm, rightMargin=1.5*cm,

        )

        usable = pw - 3*cm

        styles = getSampleStyleSheet()



        def ps(name, **kw):

            return ParagraphStyle(name, parent=styles['Normal'], **kw)



        title_s   = ps('T',  fontSize=16, fontName='Helvetica-Bold', textColor=PRIMARY, spaceAfter=1*mm)

        sub_s     = ps('S',  fontSize=9,  fontName='Helvetica', textColor=TEXT_MUTED, spaceAfter=4*mm)

        section_s = ps('Sc', fontSize=10, fontName='Helvetica-Bold', textColor=PRIMARY,

                        spaceBefore=5*mm, spaceAfter=2*mm)

        cell_s    = ps('C',  fontSize=9,  fontName='Helvetica', textColor=TEXT_DARK, leading=13)

        cell_r    = ps('Cr', fontSize=9,  fontName='Helvetica', textColor=TEXT_DARK,

                        leading=13, alignment=TA_RIGHT)

        hdr_s     = ps('H',  fontSize=8,  fontName='Helvetica-Bold', textColor=colors.white, leading=12)

        hdr_r     = ps('Hr', fontSize=8,  fontName='Helvetica-Bold', textColor=colors.white,

                        leading=12, alignment=TA_RIGHT)

        lbl_s     = ps('L',  fontSize=8,  fontName='Helvetica', textColor=TEXT_MUTED, leading=12)

        val_s     = ps('V',  fontSize=11, fontName='Helvetica-Bold', textColor=TEXT_DARK, leading=14)

        green_v   = ps('GV', fontSize=11, fontName='Helvetica-Bold', textColor=SUCCESS, leading=14)

        amber_v   = ps('AV', fontSize=11, fontName='Helvetica-Bold', textColor=AMBER, leading=14)

        red_v     = ps('RV', fontSize=11, fontName='Helvetica-Bold', textColor=DANGER, leading=14)

        blue_v    = ps('BV', fontSize=11, fontName='Helvetica-Bold', textColor=ACCENT, leading=14)

        white_v   = ps('WV', fontSize=12, fontName='Helvetica-Bold', textColor=colors.white, leading=15)

        white_l   = ps('WL', fontSize=8,  fontName='Helvetica', textColor=colors.HexColor('#94a3b8'), leading=12)

        muted_c   = ps('Mc', fontSize=8,  fontName='Helvetica', textColor=TEXT_MUTED, leading=12, alignment=TA_RIGHT)



        def page_footer(canvas, doc):
            draw_pdf_page_chrome(canvas, doc, title='Dashboard Summary', header_right_line2=f'Generated: {today.strftime("%d %B %Y")}')



        elements = []



        # -- Title -------------------------------------------------

        elements.append(Paragraph('Dashboard Summary', title_s))

        elements.append(Paragraph(

            f'As of {today.strftime("%d %B %Y")}  |  {active_members} active members',

            sub_s,

        ))

        elements.append(HRFlowable(width='100%', thickness=1, color=ACCENT, spaceAfter=4*mm))



        # -- Key metrics grid (3 × 2) ------------------------------

        def stat_cell(label, value, value_style=None):

            return [Paragraph(label, lbl_s), Paragraph(value, value_style or val_s)]



        half = usable / 2 - 3*mm

        metrics = [

            [

                Table([stat_cell('Total Members', str(total_members), blue_v)],

                      colWidths=[half*0.55, half*0.45]),

                Table([stat_cell('Active Members', str(active_members), blue_v)],

                      colWidths=[half*0.55, half*0.45]),

            ],

            [

                Table([stat_cell('Total Contributions', f'KES {total_contributions:,.0f}', green_v)],

                      colWidths=[half*0.55, half*0.45]),

                Table([stat_cell('Registration Fees', f'KES {total_reg_fees:,.0f}', green_v)],

                      colWidths=[half*0.55, half*0.45]),

            ],

            [

                Table([stat_cell('Total Loans Given', f'KES {total_loans_given:,.0f}', amber_v)],

                      colWidths=[half*0.55, half*0.45]),

                Table([stat_cell('Total Loan Paid', f'KES {total_loan_paid:,.0f}', green_v)],

                      colWidths=[half*0.55, half*0.45]),

            ],

            [

                Table([stat_cell('Interest Collected', f'KES {interest_collected:,.0f}', green_v)],

                      colWidths=[half*0.55, half*0.45]),

                Table([stat_cell('Penalties Collected', f'KES {total_penalties:,.0f}', green_v)],

                      colWidths=[half*0.55, half*0.45]),

            ],

            [

                Table([stat_cell('Outstanding Balance', f'KES {total_loan_balance:,.0f}', red_v)],

                      colWidths=[half*0.55, half*0.45]),

                Table([stat_cell('Total Income', f'KES {total_income:,.0f}', blue_v)],

                      colWidths=[half*0.55, half*0.45]),

            ],

        ]

        for inner in metrics:

            for t in inner:

                t.setStyle(TableStyle([

                    ('BACKGROUND',    (0, 0), (-1, -1), ALT_ROW),

                    ('GRID',          (0, 0), (-1, -1), 0.4, BORDER),

                    ('TOPPADDING',    (0, 0), (-1, -1), 8),

                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),

                    ('LEFTPADDING',   (0, 0), (-1, -1), 10),

                    ('RIGHTPADDING',  (0, 0), (-1, -1), 6),

                    ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),

                ]))



        grid = Table(metrics, colWidths=[half + 3*mm, half + 3*mm], hAlign='LEFT')

        grid.setStyle(TableStyle([

            ('LEFTPADDING',  (0, 0), (-1, -1), 3),

            ('RIGHTPADDING', (0, 0), (-1, -1), 3),

            ('TOPPADDING',   (0, 0), (-1, -1), 3),

            ('BOTTOMPADDING',(0, 0), (-1, -1), 3),

        ]))

        elements.append(grid)



        # -- Treasurer Balance highlight ---------------------------

        elements.append(Spacer(1, 4*mm))

        tb_data = [[

            Paragraph('TREASURER BALANCE', ps('tbl', fontSize=9, fontName='Helvetica-Bold',

                       textColor=colors.HexColor('#4ade80'), leading=12)),

            Paragraph(f'KES {treasurer_balance:,.2f}',

                      ps('tbv', fontSize=18, fontName='Helvetica-Bold',

                         textColor=colors.white, leading=22, alignment=TA_RIGHT)),

        ], [

            Paragraph(

                f'Income: KES {total_income:,.0f}  |  '

                f'Contributions: KES {float(total_contributions):,.0f}  |  '

                f'Interest: KES {interest_collected:,.0f}  |  '

                f'Penalties: KES {total_penalties:,.0f}',

                ps('tbs', fontSize=8, fontName='Helvetica', textColor=colors.HexColor('#94a3b8'), leading=11)

            ),

            Paragraph('', lbl_s),

        ]]

        tb_tbl = Table(tb_data, colWidths=[usable * 0.45, usable * 0.55])

        tb_tbl.setStyle(TableStyle([

            ('BACKGROUND',    (0, 0), (-1, -1), NAVY_BG),

            ('SPAN',          (0, 1), (-1, 1)),

            ('TOPPADDING',    (0, 0), (-1, -1), 10),

            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),

            ('LEFTPADDING',   (0, 0), (-1, -1), 14),

            ('RIGHTPADDING',  (0, 0), (-1, -1), 14),

            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),

            ('ROUNDEDCORNERS', [4]),

        ]))

        elements.append(tb_tbl)



        # -- Loan portfolio breakdown ------------------------------

        elements.append(Paragraph('Loan Portfolio', section_s))

        loan_data = [

            [Paragraph('STATUS', hdr_s), Paragraph('COUNT', hdr_r),

             Paragraph('OUTSTANDING (KES)', hdr_r)],

            [Paragraph('Active', cell_s), Paragraph(str(active_count), cell_r),

             Paragraph(f'{principal_outstanding:,.2f}', cell_r)],

            [Paragraph('Late', ps('late', fontSize=9, fontName='Helvetica-Bold',

                                   textColor=DANGER, leading=13)),

             Paragraph(str(late_count), cell_r),

             Paragraph(f'{outstanding_interest:,.2f}', cell_r)],

            [Paragraph('Cleared', ps('cl', fontSize=9, fontName='Helvetica',

                                      textColor=SUCCESS, leading=13)),

             Paragraph(str(cleared_count), cell_r),

             Paragraph('', muted_c)],

            [Paragraph('Total Balance', ps('tot', fontSize=9, fontName='Helvetica-Bold',

                                            textColor=TEXT_DARK, leading=13)),

             Paragraph(str(active_count + late_count + cleared_count), cell_r),

             Paragraph(f'KES {total_loan_balance:,.2f}',

                       ps('totv', fontSize=9, fontName='Helvetica-Bold',

                           textColor=DANGER, leading=13, alignment=TA_RIGHT))],

        ]

        loan_tbl = Table(loan_data, colWidths=[usable*0.40, usable*0.25, usable*0.35], repeatRows=1)

        loan_tbl.setStyle(TableStyle([

            ('BACKGROUND',    (0, 0), (-1, 0), PRIMARY),

            ('ROWBACKGROUNDS',(0, 1), (-1, -2), [colors.white, ALT_ROW]),

            ('BACKGROUND',    (0, -1), (-1, -1), colors.HexColor('#fff1f2')),

            ('GRID',          (0, 0), (-1, -1), 0.4, BORDER),

            ('LINEBELOW',     (0, 0), (-1, 0), 1.5, ACCENT),

            ('LINEABOVE',     (0, -1), (-1, -1), 1, DANGER),

            ('TOPPADDING',    (0, 0), (-1, -1), 7),

            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),

            ('LEFTPADDING',   (0, 0), (-1, -1), 10),

            ('RIGHTPADDING',  (0, 0), (-1, -1), 10),

            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),

        ]))

        elements.append(loan_tbl)



        # -- Contributions by month (this year) -------------------

        elements.append(Paragraph(f'Contributions by Month  {today.year}', section_s))

        month_rows = [[

            Paragraph('MONTH', hdr_s),

            Paragraph('AMOUNT (KES)', hdr_r),

        ]]

        for i, name in enumerate(month_names, 1):

            amt = contrib_monthly.get(i, 0)

            month_rows.append([

                Paragraph(name, cell_s),

                Paragraph(f'{amt:,.2f}' if amt else '', cell_r if amt else muted_c),

            ])

        total_this_year = sum(contrib_monthly.values())

        month_rows.append([

            Paragraph('Total', ps('mt', fontSize=9, fontName='Helvetica-Bold',

                                   textColor=TEXT_DARK, leading=13)),

            Paragraph(f'KES {total_this_year:,.2f}',

                      ps('mv', fontSize=9, fontName='Helvetica-Bold',

                          textColor=SUCCESS, leading=13, alignment=TA_RIGHT)),

        ])

        month_tbl = Table(month_rows, colWidths=[usable*0.4, usable*0.6], repeatRows=1)

        month_tbl.setStyle(TableStyle([

            ('BACKGROUND',    (0, 0),  (-1, 0),  PRIMARY),

            ('ROWBACKGROUNDS',(0, 1),  (-1, -2), [colors.white, ALT_ROW]),

            ('BACKGROUND',    (0, -1), (-1, -1), GREEN_BG),

            ('GRID',          (0, 0),  (-1, -1), 0.4, BORDER),

            ('LINEBELOW',     (0, 0),  (-1, 0),  1.5, ACCENT),

            ('LINEABOVE',     (0, -1), (-1, -1), 1,   SUCCESS),

            ('TOPPADDING',    (0, 0),  (-1, -1), 6),

            ('BOTTOMPADDING', (0, 0),  (-1, -1), 6),

            ('LEFTPADDING',   (0, 0),  (-1, -1), 10),

            ('RIGHTPADDING',  (0, 0),  (-1, -1), 10),

            ('VALIGN',        (0, 0),  (-1, -1), 'MIDDLE'),

        ]))



        # Put loan portfolio and monthly contributions side by side

        two_col = Table(

            [[loan_tbl, month_tbl]],

            colWidths=[usable*0.48, usable*0.52],

        )

        two_col.setStyle(TableStyle([

            ('LEFTPADDING',  (0, 0), (-1, -1), 0),

            ('RIGHTPADDING', (0, 0), (-1, -1), 0),

            ('TOPPADDING',   (0, 0), (-1, -1), 0),

            ('BOTTOMPADDING',(0, 0), (-1, -1), 0),

            ('VALIGN',       (0, 0), (-1, -1), 'TOP'),

        ]))

        elements.append(Spacer(1, -4*mm))  # pull up after the section heading

        elements.append(two_col)



        # -- Recent Activity ---------------------------------------

        elements.append(Paragraph('Recent Contributions', section_s))

        rc_data = [

            [Paragraph('MEMBER', hdr_s), Paragraph('MONTH / YEAR', hdr_s),

             Paragraph('AMOUNT', hdr_r), Paragraph('DATE', hdr_s)],

        ]

        for c in recent_contributions:

            rc_data.append([

                Paragraph(c.member.name, cell_s),

                Paragraph(f'{c.get_month_display()} {c.year}', cell_s),

                Paragraph(f'KES {c.amount:,.2f}',

                          ps('rv', fontSize=9, fontName='Helvetica',

                             textColor=SUCCESS, leading=13, alignment=TA_RIGHT)),

                Paragraph(str(c.date), cell_s),

            ])

        if len(rc_data) == 1:

            rc_data.append([Paragraph('No contributions.', cell_s),

                             Paragraph(''), Paragraph(''), Paragraph('')])

        rc_tbl = Table(rc_data,

                       colWidths=[usable*0.30, usable*0.25, usable*0.22, usable*0.23],

                       repeatRows=1)

        rc_tbl.setStyle(TableStyle([

            ('BACKGROUND',    (0, 0), (-1, 0), PRIMARY),

            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, ALT_ROW]),

            ('GRID',          (0, 0), (-1, -1), 0.4, BORDER),

            ('LINEBELOW',     (0, 0), (-1, 0), 1.5, ACCENT),

            ('TOPPADDING',    (0, 0), (-1, -1), 6),

            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),

            ('LEFTPADDING',   (0, 0), (-1, -1), 8),

            ('RIGHTPADDING',  (0, 0), (-1, -1), 8),

            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),

        ]))

        elements.append(rc_tbl)



        elements.append(Paragraph('Recent Loans', section_s))

        rl_data = [

            [Paragraph('MEMBER', hdr_s), Paragraph('AMOUNT', hdr_r),

             Paragraph('BALANCE', hdr_r), Paragraph('STATUS', hdr_s),

             Paragraph('DATE', hdr_s)],

        ]

        for l in recent_loans:

            if l.status == 'cleared':

                st = Paragraph('Cleared', ps(f'lsc{l.pk}', fontSize=8, fontName='Helvetica-Bold',

                                              textColor=SUCCESS, leading=11))

            elif l.status == 'late':

                st = Paragraph('Late', ps(f'lsl{l.pk}', fontSize=8, fontName='Helvetica-Bold',

                                           textColor=DANGER, leading=11))

            else:

                st = Paragraph('Active', ps(f'lsa{l.pk}', fontSize=8, fontName='Helvetica-Bold',

                                             textColor=AMBER, leading=11))

            rl_data.append([

                Paragraph(l.member.name, cell_s),

                Paragraph(f'KES {l.loan_amount:,.2f}',

                          ps('la', fontSize=9, fontName='Helvetica',

                             textColor=AMBER, leading=13, alignment=TA_RIGHT)),

                Paragraph(f'KES {l.balance:,.2f}',

                          ps('lb', fontSize=9, fontName='Helvetica-Bold',

                             textColor=DANGER if l.balance > 0 else SUCCESS,

                             leading=13, alignment=TA_RIGHT)),

                st,

                Paragraph(str(l.date_taken), cell_s),

            ])

        if len(rl_data) == 1:

            rl_data.append([Paragraph('No loans.', cell_s),

                             Paragraph(''), Paragraph(''), Paragraph(''), Paragraph('')])

        rl_tbl = Table(rl_data,

                       colWidths=[usable*0.28, usable*0.22, usable*0.20, usable*0.15, usable*0.15],

                       repeatRows=1)

        rl_tbl.setStyle(TableStyle([

            ('BACKGROUND',    (0, 0), (-1, 0), PRIMARY),

            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, ALT_ROW]),

            ('GRID',          (0, 0), (-1, -1), 0.4, BORDER),

            ('LINEBELOW',     (0, 0), (-1, 0), 1.5, ACCENT),

            ('TOPPADDING',    (0, 0), (-1, -1), 6),

            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),

            ('LEFTPADDING',   (0, 0), (-1, -1), 8),

            ('RIGHTPADDING',  (0, 0), (-1, -1), 8),

            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),

        ]))

        elements.append(rl_tbl)



        # -- Build -------------------------------------------------

        doc.build(elements, onFirstPage=page_footer, onLaterPages=page_footer)

        pdf = buffer.getvalue()

        buffer.close()

        response.write(pdf)

        return response




