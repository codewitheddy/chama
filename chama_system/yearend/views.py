from utils.exports import _get_group_name, _get_document_footer, draw_pdf_page_chrome, _get_document_footer, draw_pdf_page_chrome
from django.views.generic import ListView, CreateView, DetailView, TemplateView
from django.views import View
from django.urls import reverse_lazy
from django.http import HttpResponse
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from decimal import Decimal, ROUND_DOWN
from io import BytesIO

from accounts.mixins import TreasurerRequiredMixin, MemberAccessMixin
from members.models import Member
from contributions.models import Contribution
from penalties.models import Penalty
from loans.models import Loan
from utils.financials import get_available_fund_balance

from .models import YearEndWithdrawal, MemberInterestShare, YearEndMemberStatus
from .forms import YearEndWithdrawalForm


def _compute_year_end_distribution(
    members,
    financial_year=None,
    include_loan_interest=True,
    include_penalties=True,
    include_other_income=False,
    include_registration_fees=False,
    include_investment_returns=True,
    deduct_expenses=True,
):
    """
    Compute the year-end distribution for all active members with customizable
    revenue stream inclusion / accumulation policy.

    Step 1: Each member receives their principal savings (total contributions) back.
    Step 2: Selected gross revenue streams are pooled:
            - Loan Interest Collected (if include_loan_interest)
            - Penalties / Fines Paid (if include_penalties)
            - Other / External Income (if include_other_income)
            - Registration Fees (if include_registration_fees)
            - Investment Returns & Dividends (if include_investment_returns)
            Less: Group Fund Expenses (if deduct_expenses)
    Step 3: Unselected revenue streams are retained in the group treasury and
            carried forward to accumulate for future financial years.
    Step 4: Distributable profit pool is shared PROPORTIONATELY to each member's
            share contributions:
            member_share = (member_contributions / total_contributions) × profit_pool
    """
    from contributions.models import Contribution
    from penalties.models import Penalty
    from loans.models import Loan

    # ── 1. Contributions (Principal Base) ───────────────────────────
    total_contributions_income = (
        Contribution.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    )

    # ── 2. Available Gross Revenue Streams ──────────────────────────
    # Loan Interest collected
    from django.db.models import F, ExpressionWrapper, DecimalField
    loans_qs = Loan.objects.annotate(
        interest_charged=ExpressionWrapper(
            F('total_payable') - F('loan_amount'),
            output_field=DecimalField(),
        )
    ).only('amount_paid', 'total_payable', 'loan_amount')
    interest_collected = sum(
        min(l.amount_paid, l.interest_charged) for l in loans_qs
    )

    # Penalties paid
    total_penalties_income = (
        Penalty.objects.filter(paid=True).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    )

    # Other income
    try:
        from other_income.models import OtherIncome
        total_other_income = (
            OtherIncome.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        )
    except Exception:
        total_other_income = Decimal('0')

    # Registration fees
    try:
        from members.models import Member as _Member
        total_reg_fees = (
            _Member.objects.aggregate(t=Sum('registration_fee_paid'))['t'] or Decimal('0')
        )
    except Exception:
        total_reg_fees = Decimal('0')

    # Investment returns / dividends
    try:
        from investments.models import InvestmentReturn
        total_investment_returns = (
            InvestmentReturn.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        )
    except Exception:
        total_investment_returns = Decimal('0')

    # Group fund expenses
    try:
        from expenses.models import Expense
        total_group_expenses = (
            Expense.objects.filter(fund_source='group_funds')
            .aggregate(t=Sum('amount'))['t'] or Decimal('0')
        )
    except Exception:
        total_group_expenses = Decimal('0')

    # ── 3. Apply Inclusion & Exclusion Selections ──────────────────
    loan_interest_selected = Decimal(str(interest_collected)) if include_loan_interest else Decimal('0')
    loan_interest_retained = Decimal(str(interest_collected)) if not include_loan_interest else Decimal('0')

    penalties_selected = total_penalties_income if include_penalties else Decimal('0')
    penalties_retained = total_penalties_income if not include_penalties else Decimal('0')

    other_income_selected = total_other_income if include_other_income else Decimal('0')
    other_income_retained = total_other_income if not include_other_income else Decimal('0')

    reg_fees_selected = total_reg_fees if include_registration_fees else Decimal('0')
    reg_fees_retained = total_reg_fees if not include_registration_fees else Decimal('0')

    investment_returns_selected = total_investment_returns if include_investment_returns else Decimal('0')
    investment_returns_retained = total_investment_returns if not include_investment_returns else Decimal('0')

    expenses_deducted = total_group_expenses if deduct_expenses else Decimal('0')

    # Gross revenue selected for profit distribution
    gross_revenue_selected = (
        loan_interest_selected
        + penalties_selected
        + other_income_selected
        + reg_fees_selected
        + investment_returns_selected
    )

    # Total revenue available across all streams
    total_revenue_available = (
        Decimal(str(interest_collected))
        + total_penalties_income
        + total_other_income
        + total_reg_fees
        + total_investment_returns
    )

    # Retained funds: Unchecked streams that accumulate for next financial year
    retained_funds = (
        loan_interest_retained
        + penalties_retained
        + other_income_retained
        + reg_fees_retained
        + investment_returns_retained
    )

    # Distributable profit pool after expense deductions
    distributable_profit_pool = max(gross_revenue_selected - expenses_deducted, Decimal('0'))
    remaining_balance = distributable_profit_pool

    # Total income evaluated (contributions + gross evaluated revenue)
    total_income = total_contributions_income + total_revenue_available

    # ── 4. Per-Member Distribution ─────────────────────────────────
    member_ids = [m.pk for m in members]
    contrib_map = dict(
        Contribution.objects.filter(member_id__in=member_ids)
        .values('member_id')
        .annotate(total=Sum('amount'))
        .values_list('member_id', 'total')
    )

    member_breakdown = []
    total_principal_back = Decimal('0')
    total_member_contributions = Decimal('0')

    for m in members:
        contrib = Decimal(str(contrib_map.get(m.pk, 0) or 0))
        reg_fee = m.registration_fee_paid or Decimal('0')
        principal = contrib          # contributions returned as principal
        total_principal_back += principal
        total_member_contributions += contrib
        member_breakdown.append({
            'member':        m,
            'contributions': contrib,
            'reg_fee':       reg_fee,
            'principal_back': principal,
        })

    # Proportional profit share per member based on contributions
    for row in member_breakdown:
        if total_member_contributions > 0 and remaining_balance > 0:
            row['interest_share'] = (
                (row['contributions'] / total_member_contributions) * remaining_balance
            ).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        elif remaining_balance > 0 and len(member_breakdown) > 0:
            row['interest_share'] = (
                (remaining_balance / len(member_breakdown)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            )
        else:
            row['interest_share'] = Decimal('0.00')

        # Deduct outstanding loans and unpaid penalties
        m = row['member']
        outstanding_loans = m.total_loan_balance() if hasattr(m, 'total_loan_balance') else Decimal('0.00')
        outstanding_penalties = m.total_penalties_unpaid() if hasattr(m, 'total_penalties_unpaid') else Decimal('0.00')
        gross_return = row['principal_back'] + row['interest_share']
        total_deductions = outstanding_loans + outstanding_penalties
        net_return = max(gross_return - total_deductions, Decimal('0.00'))
        deficit = max(total_deductions - gross_return, Decimal('0.00'))

        row['gross_return'] = gross_return
        row['outstanding_loans'] = outstanding_loans
        row['outstanding_penalties'] = outstanding_penalties
        row['total_deductions'] = total_deductions
        row['total'] = net_return
        row['net_total'] = net_return
        row['deficit'] = deficit

    total_interest_shared = sum(r['interest_share'] for r in member_breakdown)
    total_gross_return = sum(r['gross_return'] for r in member_breakdown)
    total_deductions_all = sum(r['total_deductions'] for r in member_breakdown)
    total_payout = sum(r['total'] for r in member_breakdown)

    return {
        'member_breakdown':          member_breakdown,
        'total_contributions_back':  total_contributions_income,
        'total_reg_fees_back':       reg_fees_selected,
        'total_principal_back':      total_principal_back,
        'total_gross_return':        total_gross_return,
        'total_deductions_all':      total_deductions_all,
        'remaining_balance':         remaining_balance,
        'distributable_profit_pool': distributable_profit_pool,
        'total_interest_shared':     total_interest_shared,
        'total_payout':              total_payout,
        'member_count':              len(member_breakdown),
        'total_income':              total_income,
        'total_member_contributions': total_member_contributions,
        'total_group_expenses':      total_group_expenses,
        'expenses_deducted':         expenses_deducted,
        'retained_funds':            retained_funds,
        'total_revenue_available':   total_revenue_available,
        'gross_revenue_selected':    gross_revenue_selected,
        # Available stream balances for display:
        'interest_collected':        interest_collected,
        'total_penalties_income':    total_penalties_income,
        'total_other_income':        total_other_income,
        'total_reg_fees':            total_reg_fees,
        'total_investment_returns':  total_investment_returns,
        # Booleans:
        'include_loan_interest':     include_loan_interest,
        'include_penalties':         include_penalties,
        'include_other_income':      include_other_income,
        'include_registration_fees': include_registration_fees,
        'include_investment_returns': include_investment_returns,
        'deduct_expenses':           deduct_expenses,
    }


class YearEndListView(TreasurerRequiredMixin, ListView):
    model = YearEndWithdrawal
    template_name = 'yearend/yearend_list.html'
    context_object_name = 'withdrawals'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['available_fund_balance'] = get_available_fund_balance()
        return ctx


class YearEndPreviewView(TreasurerRequiredMixin, TemplateView):
    """Live read-only preview of what each member would receive at year-end closing."""
    template_name = 'yearend/yearend_preview.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        members = list(Member.objects.filter(is_active=True).order_by('name'))
        get = self.request.GET

        include_loan_interest = get.get('include_loan_interest', '1') in ['1', 'true', 'True', 'on'] if 'include_loan_interest' in get else True
        include_penalties = get.get('include_penalties', '1') in ['1', 'true', 'True', 'on'] if 'include_penalties' in get else True
        include_other_income = get.get('include_other_income', '0') in ['1', 'true', 'True', 'on'] if 'include_other_income' in get else False
        include_registration_fees = get.get('include_registration_fees', '0') in ['1', 'true', 'True', 'on'] if 'include_registration_fees' in get else False
        include_investment_returns = get.get('include_investment_returns', '1') in ['1', 'true', 'True', 'on'] if 'include_investment_returns' in get else True
        deduct_expenses = get.get('deduct_expenses', '1') in ['1', 'true', 'True', 'on'] if 'deduct_expenses' in get else True

        distribution = _compute_year_end_distribution(
            members,
            include_loan_interest=include_loan_interest,
            include_penalties=include_penalties,
            include_other_income=include_other_income,
            include_registration_fees=include_registration_fees,
            include_investment_returns=include_investment_returns,
            deduct_expenses=deduct_expenses,
        )
        ctx.update(distribution)
        ctx['available_fund_balance'] = get_available_fund_balance()
        return ctx


class YearEndPreviewPDFView(TreasurerRequiredMixin, View):
    """PDF export of the live year-end distribution preview."""

    def get(self, request):
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import cm, mm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_RIGHT
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph,
            Spacer, HRFlowable,
        )
        from django.utils import timezone

        members = list(Member.objects.filter(is_active=True).order_by('name'))
        get = request.GET

        include_loan_interest = get.get('include_loan_interest', '1') in ['1', 'true', 'True', 'on'] if 'include_loan_interest' in get else True
        include_penalties = get.get('include_penalties', '1') in ['1', 'true', 'True', 'on'] if 'include_penalties' in get else True
        include_other_income = get.get('include_other_income', '0') in ['1', 'true', 'True', 'on'] if 'include_other_income' in get else False
        include_registration_fees = get.get('include_registration_fees', '0') in ['1', 'true', 'True', 'on'] if 'include_registration_fees' in get else False
        include_investment_returns = get.get('include_investment_returns', '1') in ['1', 'true', 'True', 'on'] if 'include_investment_returns' in get else True
        deduct_expenses = get.get('deduct_expenses', '1') in ['1', 'true', 'True', 'on'] if 'deduct_expenses' in get else True

        d = _compute_year_end_distribution(
            members,
            include_loan_interest=include_loan_interest,
            include_penalties=include_penalties,
            include_other_income=include_other_income,
            include_registration_fees=include_registration_fees,
            include_investment_returns=include_investment_returns,
            deduct_expenses=deduct_expenses,
        )

        PRIMARY    = colors.HexColor('#1e3a5f')
        ACCENT     = colors.HexColor('#2563eb')
        SUCCESS    = colors.HexColor('#16a34a')
        AMBER      = colors.HexColor('#d97706')
        BLUE       = colors.HexColor('#2563eb')
        PURPLE     = colors.HexColor('#7c3aed')
        ALT_ROW    = colors.HexColor('#f8fafc')
        BORDER     = colors.HexColor('#cbd5e1')
        TEXT_DARK  = colors.HexColor('#1e293b')
        TEXT_MUTED = colors.HexColor('#64748b')
        GREEN_BG   = colors.HexColor('#f0fdf4')

        today_str  = timezone.localdate().strftime('%d %B %Y')
        title      = f'Year-End Distribution Preview — {today_str}'

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="yearend_preview_{timezone.localdate().year}.pdf"'
        )

        buffer = BytesIO()
        pw, ph = A4
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            topMargin=32*mm, bottomMargin=16*mm,
            leftMargin=1.5*cm, rightMargin=1.5*cm,
        )

        styles = getSampleStyleSheet()

        def ps(name, **kw):
            return ParagraphStyle(name, parent=styles['Normal'], **kw)

        title_s   = ps('T',  fontSize=15, fontName='Helvetica-Bold',
                        textColor=PRIMARY, spaceAfter=1*mm)
        sub_s     = ps('S',  fontSize=9,  fontName='Helvetica',
                        textColor=TEXT_MUTED, spaceAfter=4*mm)
        section_s = ps('Sc', fontSize=10, fontName='Helvetica-Bold',
                        textColor=PRIMARY, spaceBefore=4*mm, spaceAfter=2*mm)
        cell_s    = ps('C',  fontSize=8,  fontName='Helvetica',
                        textColor=TEXT_DARK, leading=11)
        cell_r    = ps('Cr', fontSize=8,  fontName='Helvetica',
                        textColor=TEXT_DARK, leading=11, alignment=TA_RIGHT)
        hdr_s     = ps('H',  fontSize=8,  fontName='Helvetica-Bold',
                        textColor=colors.white, leading=11)
        hdr_r     = ps('Hr', fontSize=8,  fontName='Helvetica-Bold',
                        textColor=colors.white, leading=11, alignment=TA_RIGHT)
        tot_s     = ps('Tt', fontSize=8,  fontName='Helvetica-Bold',
                        textColor=TEXT_DARK, leading=11)
        tot_r     = ps('Tr', fontSize=8,  fontName='Helvetica-Bold',
                        textColor=TEXT_DARK, leading=11, alignment=TA_RIGHT)
        green_r   = ps('Gr', fontSize=8,  fontName='Helvetica-Bold',
                        textColor=SUCCESS,   leading=11, alignment=TA_RIGHT)
        amber_r   = ps('Ar', fontSize=8,  fontName='Helvetica',
                        textColor=AMBER,     leading=11, alignment=TA_RIGHT)
        blue_r    = ps('Br', fontSize=8,  fontName='Helvetica',
                        textColor=BLUE,      leading=11, alignment=TA_RIGHT)
        muted_r   = ps('Mr', fontSize=8,  fontName='Helvetica',
                        textColor=TEXT_MUTED, leading=11, alignment=TA_RIGHT)
        red_r     = ps('Rr', fontSize=8,  fontName='Helvetica',
                        textColor=colors.HexColor('#dc2626'), leading=11, alignment=TA_RIGHT)

        def page_footer(canvas, doc):
            draw_pdf_page_chrome(canvas, doc, title='Year-End Distribution Preview', header_right_line2=f'Generated: {today_str}')

        usable = pw - 3*cm
        elements = []

        elements.append(Paragraph('Year-End Distribution Preview', title_s))
        elements.append(Paragraph(
            f'Live estimate as of {today_str}  |  {d["member_count"]} active member(s)  |  '
            f'Not an official record — actual payouts are set at closing.',
            sub_s,
        ))
        elements.append(HRFlowable(width='100%', thickness=1, color=ACCENT, spaceAfter=3*mm))

        # Summary strip (5 columns: Revenue, Distributable, Retained, Principal, Total Payout)
        summary_data = [[
            Paragraph('Gross Revenue', ps('lbl', fontSize=8, fontName='Helvetica', textColor=TEXT_MUTED, leading=11)),
            Paragraph('Distributable Pool', ps('lbl2', fontSize=8, fontName='Helvetica', textColor=TEXT_MUTED, leading=11)),
            Paragraph('Retained / Carried Fwd', ps('lbl3', fontSize=8, fontName='Helvetica', textColor=TEXT_MUTED, leading=11)),
            Paragraph('Principal Back', ps('lbl4', fontSize=8, fontName='Helvetica', textColor=TEXT_MUTED, leading=11)),
            Paragraph('Total Payout', ps('lbl5', fontSize=8, fontName='Helvetica', textColor=TEXT_MUTED, leading=11)),
        ], [
            Paragraph(f'KES {d["total_revenue_available"]:,.2f}', ps('v1', fontSize=9, fontName='Helvetica-Bold', textColor=BLUE, leading=13)),
            Paragraph(f'KES {d["distributable_profit_pool"]:,.2f}', ps('v2', fontSize=9, fontName='Helvetica-Bold', textColor=AMBER, leading=13)),
            Paragraph(f'KES {d["retained_funds"]:,.2f}', ps('v3', fontSize=9, fontName='Helvetica-Bold', textColor=PURPLE, leading=13)),
            Paragraph(f'KES {d["total_principal_back"]:,.2f}', ps('v4', fontSize=9, fontName='Helvetica-Bold', textColor=TEXT_DARK, leading=13)),
            Paragraph(f'KES {d["total_payout"]:,.2f}', ps('v5', fontSize=9, fontName='Helvetica-Bold', textColor=SUCCESS, leading=13)),
        ]]
        summary_tbl = Table(summary_data, colWidths=[usable/5]*5)
        summary_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor('#f0f4ff')),
            ('GRID',          (0, 0), (-1, -1), 0.5, BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(summary_tbl)
        elements.append(Spacer(1, 4*mm))

        # Per-member table
        elements.append(Paragraph('Per-Member Expected Payout', section_s))

        col_w = [usable*0.04, usable*0.22, usable*0.13, usable*0.13,
                 usable*0.13, usable*0.14, usable*0.14, usable*0.07]

        headers = [
            Paragraph('#', hdr_s),
            Paragraph('Member', hdr_s),
            Paragraph('Contributions', hdr_r),
            Paragraph('Principal Back', hdr_r),
            Paragraph('Profit Share', hdr_r),
            Paragraph('Less Deductions', hdr_r),
            Paragraph('Net Payout', hdr_r),
            Paragraph('Share', hdr_r),
        ]
        rows = [headers]

        total_contrib = d['total_member_contributions']
        for i, row in enumerate(d['member_breakdown'], 1):
            share_pct = (
                f"{(row['contributions'] / total_contrib * 100):.1f}%"
                if total_contrib else '—'
            )
            ded_str = f"- {row['total_deductions']:,.2f}" if row['total_deductions'] > 0 else "—"
            ded_style = red_r if row['total_deductions'] > 0 else muted_r
            rows.append([
                Paragraph(str(i), cell_s),
                Paragraph(row['member'].name, cell_s),
                Paragraph(f'{row["contributions"]:,.2f}', cell_r),
                Paragraph(f'{row["principal_back"]:,.2f}', blue_r),
                Paragraph(f'{row["interest_share"]:,.2f}', amber_r),
                Paragraph(ded_str, ded_style),
                Paragraph(f'{row["total"]:,.2f}', green_r),
                Paragraph(share_pct, muted_r),
            ])

        # Totals footer
        tot_ded_str = f"- {d['total_deductions_all']:,.2f}" if d.get('total_deductions_all', 0) > 0 else "—"
        tot_ded_style = red_r if d.get('total_deductions_all', 0) > 0 else tot_r
        rows.append([
            Paragraph('', tot_s),
            Paragraph('Total', tot_s),
            Paragraph(f'{d["total_contributions_back"]:,.2f}', tot_r),
            Paragraph(f'{d["total_principal_back"]:,.2f}', tot_r),
            Paragraph(f'{d["total_interest_shared"]:,.2f}', tot_r),
            Paragraph(tot_ded_str, tot_ded_style),
            Paragraph(f'{d["total_payout"]:,.2f}',
                      ps('gtr', fontSize=8, fontName='Helvetica-Bold',
                         textColor=SUCCESS, leading=11, alignment=TA_RIGHT)),
            Paragraph('100%', tot_r),
        ])

        tbl = Table(rows, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0),  (-1, 0),  PRIMARY),
            ('ROWBACKGROUNDS',(0, 1),  (-1, -2), [colors.white, ALT_ROW]),
            ('BACKGROUND',    (0, -1), (-1, -1), GREEN_BG),
            ('GRID',          (0, 0),  (-1, -1), 0.4, BORDER),
            ('LINEBELOW',     (0, 0),  (-1, 0),  1.5, ACCENT),
            ('LINEABOVE',     (0, -1), (-1, -1), 1,   SUCCESS),
            ('TOPPADDING',    (0, 0),  (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0),  (-1, -1), 5),
            ('LEFTPADDING',   (0, 0),  (-1, -1), 5),
            ('RIGHTPADDING',  (0, 0),  (-1, -1), 5),
            ('VALIGN',        (0, 0),  (-1, -1), 'MIDDLE'),
        ]))
        elements.append(tbl)

        doc.build(elements, onFirstPage=page_footer, onLaterPages=page_footer)
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        return response


class YearEndDetailView(TreasurerRequiredMixin, DetailView):
    model = YearEndWithdrawal
    template_name = 'yearend/yearend_detail.html'
    context_object_name = 'withdrawal'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['interest_shares'] = (
            self.object.interest_shares.select_related('member').order_by('member__name')
        )
        ctx['member_statuses'] = (
            self.object.member_statuses.select_related('member').order_by('member__name')
        )
        return ctx


class YearEndCreateView(TreasurerRequiredMixin, CreateView):
    model = YearEndWithdrawal
    form_class = YearEndWithdrawalForm
    template_name = 'yearend/yearend_form.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        members = list(Member.objects.filter(is_active=True).order_by('name'))
        distribution = _compute_year_end_distribution(
            members,
            include_loan_interest=True,
            include_penalties=True,
            include_other_income=False,
            include_registration_fees=False,
            include_investment_returns=True,
            deduct_expenses=True,
        )
        ctx.update(distribution)
        ctx['available_fund_balance'] = get_available_fund_balance()
        return ctx

    def form_valid(self, form):
        members = list(Member.objects.filter(is_active=True).order_by('name'))
        post = self.request.POST

        # --- Collect member statuses ---
        member_statuses = {}
        for m in members:
            member_statuses[m.pk] = post.get(f'status_{m.pk}', 'continuing')

        # --- Validate: exiting members must have no active/late loans ---
        exiting_with_loans = []
        for m in members:
            if member_statuses.get(m.pk) == 'exiting':
                if Loan.objects.filter(member=m, status__in=['active', 'late']).exists():
                    exiting_with_loans.append(m.name)

        if exiting_with_loans:
            names = ', '.join(exiting_with_loans)
            messages.error(
                self.request,
                f'The following members have outstanding loans and cannot exit: {names}. '
                f'Please ensure all loans are cleared before marking them as exiting.'
            )
            return self.form_invalid(form)

        # --- Extract inclusion checkboxes ---
        include_loan_interest = form.cleaned_data.get('include_loan_interest', True)
        include_penalties = form.cleaned_data.get('include_penalties', True)
        include_other_income = form.cleaned_data.get('include_other_income', False)
        include_registration_fees = form.cleaned_data.get('include_registration_fees', False)
        include_investment_returns = form.cleaned_data.get('include_investment_returns', True)
        deduct_expenses = form.cleaned_data.get('deduct_expenses', True)

        # --- Compute distribution with selections ---
        distribution = _compute_year_end_distribution(
            members,
            include_loan_interest=include_loan_interest,
            include_penalties=include_penalties,
            include_other_income=include_other_income,
            include_registration_fees=include_registration_fees,
            include_investment_returns=include_investment_returns,
            deduct_expenses=deduct_expenses,
        )

        with transaction.atomic():
            withdrawal = form.save(commit=False)
            withdrawal.recorded_by = self.request.user
            withdrawal.amount_withdrawn = distribution['total_payout']
            withdrawal.interest_shared = distribution['total_interest_shared']
            withdrawal.retained_funds = distribution['retained_funds']
            withdrawal.total_income_evaluated = distribution['total_revenue_available']
            withdrawal.include_loan_interest = include_loan_interest
            withdrawal.include_penalties = include_penalties
            withdrawal.include_other_income = include_other_income
            withdrawal.include_registration_fees = include_registration_fees
            withdrawal.include_investment_returns = include_investment_returns
            withdrawal.deduct_expenses = deduct_expenses
            withdrawal.save()

            # Save per-member interest shares (computed automatically)
            for row in distribution['member_breakdown']:
                MemberInterestShare.objects.create(
                    withdrawal=withdrawal,
                    member=row['member'],
                    amount=row['interest_share'],
                )

            # Save member statuses + update is_active for exiting members
            for m in members:
                status = member_statuses.get(m.pk, 'continuing')
                YearEndMemberStatus.objects.create(
                    withdrawal=withdrawal, member=m, status=status
                )
                if status == 'exiting':
                    Member.objects.filter(pk=m.pk).update(is_active=False)

        messages.success(
            self.request,
            f'Year-end withdrawal for {withdrawal.financial_year} recorded. '
            f'Total payout: KES {withdrawal.amount_withdrawn:,.2f} | '
            f'Retained for next financial year: KES {withdrawal.retained_funds:,.2f}'
        )
        return super(CreateView, self).form_valid(form)

    def get_success_url(self):
        return reverse_lazy('yearend:detail', kwargs={'pk': self.object.pk})


class YearEndExportPDFView(MemberAccessMixin, View):
    """Export a single year-end withdrawal record as a detailed PDF report."""

    def get(self, request, pk):
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import cm, mm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph,
            Spacer, HRFlowable, KeepTogether,
        )
        from django.utils import timezone

        withdrawal = get_object_or_404(YearEndWithdrawal, pk=pk)
        interest_shares = list(
            withdrawal.interest_shares.select_related('member').order_by('member__name')
        )
        member_statuses = list(
            withdrawal.member_statuses.select_related('member').order_by('member__name')
        )

        # ── Colours (match exports.py) ────────────────────────────
        PRIMARY    = colors.HexColor('#1e3a5f')
        ACCENT     = colors.HexColor('#2563eb')
        SUCCESS    = colors.HexColor('#16a34a')
        DANGER     = colors.HexColor('#e11d48')
        LIGHT_BG   = colors.HexColor('#f0f4ff')
        ALT_ROW    = colors.HexColor('#f8fafc')
        BORDER     = colors.HexColor('#cbd5e1')
        TEXT_DARK  = colors.HexColor('#1e293b')
        TEXT_MUTED = colors.HexColor('#64748b')
        GREEN_BG   = colors.HexColor('#f0fdf4')
        GREY_BG    = colors.HexColor('#f1f5f9')

        title = f'Year-End Report — {withdrawal.financial_year}'

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = (
            f'attachment; filename="yearend_{withdrawal.financial_year}.pdf"'
        )

        buffer = BytesIO()
        pagesize = A4
        pw, ph = pagesize

        doc = SimpleDocTemplate(
            buffer,
            pagesize=pagesize,
            topMargin=32*mm,
            bottomMargin=16*mm,
            leftMargin=1.5*cm,
            rightMargin=1.5*cm,
        )

        # ── Styles ────────────────────────────────────────────────
        styles = getSampleStyleSheet()

        def style(name, **kw):
            return ParagraphStyle(name, parent=styles['Normal'], **kw)

        title_s    = style('T', fontSize=16, fontName='Helvetica-Bold',
                           textColor=PRIMARY, spaceAfter=1*mm)
        sub_s      = style('S', fontSize=9, fontName='Helvetica',
                           textColor=TEXT_MUTED, spaceAfter=4*mm)
        section_s  = style('Sec', fontSize=11, fontName='Helvetica-Bold',
                           textColor=PRIMARY, spaceBefore=5*mm, spaceAfter=2*mm)
        label_s    = style('Lbl', fontSize=8, fontName='Helvetica',
                           textColor=TEXT_MUTED, leading=12)
        value_s    = style('Val', fontSize=9, fontName='Helvetica-Bold',
                           textColor=TEXT_DARK, leading=12)
        cell_s     = style('C', fontSize=8, fontName='Helvetica',
                           textColor=TEXT_DARK, leading=11)
        hdr_s      = style('H', fontSize=8, fontName='Helvetica-Bold',
                           textColor=colors.white, leading=11)
        total_s    = style('Tot', fontSize=8, fontName='Helvetica-Bold',
                           textColor=TEXT_DARK, leading=11)
        green_s    = style('G', fontSize=8, fontName='Helvetica-Bold',
                           textColor=SUCCESS, leading=11)
        red_s      = style('R', fontSize=8, fontName='Helvetica-Bold',
                           textColor=DANGER, leading=11)

        elements = []

        # ── Page header callback ──────────────────────────────────
        def page_footer(canvas, doc):
            draw_pdf_page_chrome(canvas, doc, title=title, header_right_line2=f'Generated: {timezone.localdate().strftime("%d %B %Y")}')

        # ── Report title ──────────────────────────────────────────
        elements.append(Paragraph(title, title_s))
        elements.append(Paragraph(
            f'Distribution date: {withdrawal.date} &nbsp;|&nbsp; '
            f'Recorded by: {withdrawal.recorded_by.get_full_name() or withdrawal.recorded_by.username} &nbsp;|&nbsp; '
            f'Recorded on: {withdrawal.created_at.strftime("%d %b %Y %H:%M")}',
            sub_s
        ))
        elements.append(HRFlowable(width='100%', thickness=1,
                                   color=ACCENT, spaceAfter=4*mm))

        # ── Summary block (2-column label/value grid) ─────────────
        elements.append(Paragraph('Summary & Distribution Policy', section_s))

        summary_data = [
            [Paragraph('Financial Year', label_s),
             Paragraph(str(withdrawal.financial_year), value_s),
             Paragraph('Distribution Date', label_s),
             Paragraph(str(withdrawal.date), value_s)],
            [Paragraph('Total Payout', label_s),
             Paragraph(f'KES {withdrawal.amount_withdrawn:,.2f}', red_s),
             Paragraph('Profit Shared', label_s),
             Paragraph(f'KES {withdrawal.interest_shared:,.2f}', green_s)],
            [Paragraph('Retained / Carried Fwd', label_s),
             Paragraph(f'KES {withdrawal.retained_funds:,.2f}', style('ret', fontSize=9, fontName='Helvetica-Bold', textColor=colors.HexColor('#7c3aed'), leading=12)),
             Paragraph('Gross Revenue Evaluated', label_s),
             Paragraph(f'KES {withdrawal.total_income_evaluated:,.2f}', value_s)],
            [Paragraph('Notes', label_s),
             Paragraph(withdrawal.notes or '—', cell_s),
             Paragraph('', label_s),
             Paragraph('', cell_s)],
        ]

        usable = pw - 3*cm
        sum_table = Table(summary_data,
                          colWidths=[usable*0.18, usable*0.32,
                                     usable*0.18, usable*0.32],
                          hAlign='LEFT')
        sum_table.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_BG),
            ('GRID',          (0, 0), (-1, -1), 0.5, BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 7),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 7),
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ('SPAN',          (1, 3), (3, 3)),   # notes spans remaining cols
        ]))
        elements.append(sum_table)
        elements.append(Spacer(1, 3*mm))

        # ── Policy streams table ──────────────────────────────────
        elements.append(Paragraph('Revenue Stream Inclusions & Accumulations', style('SubSec', fontSize=9, fontName='Helvetica-Bold', textColor=PRIMARY, spaceBefore=2*mm, spaceAfter=2*mm)))

        policy_headers = [
            Paragraph('Revenue Stream', hdr_s),
            Paragraph('Policy Status', hdr_s),
            Paragraph('Treatment & Accounting Rule', hdr_s),
        ]
        policy_rows = [policy_headers]

        streams = [
            ('Loan Interest Collected', withdrawal.include_loan_interest, 'Shared proportionately among active members' if withdrawal.include_loan_interest else 'Retained in Treasury (Accumulates for next year)'),
            ('Penalties & Fines Paid', withdrawal.include_penalties, 'Shared proportionately among active members' if withdrawal.include_penalties else 'Retained in Treasury (Accumulates for next year)'),
            ('Other / External Income', withdrawal.include_other_income, 'Shared proportionately among active members' if withdrawal.include_other_income else 'Retained in Treasury (Accumulates for next year)'),
            ('Registration Fees Fund', withdrawal.include_registration_fees, 'Shared proportionately among active members' if withdrawal.include_registration_fees else 'Retained in Registration Fee Reserve'),
            ('Investment Returns', withdrawal.include_investment_returns, 'Shared proportionately among active members' if withdrawal.include_investment_returns else 'Retained in Treasury (Accumulates for next year)'),
            ('Group Fund Expenses', withdrawal.deduct_expenses, 'Deducted from gross profit pool before sharing' if withdrawal.deduct_expenses else 'Not deducted from distributable pool'),
        ]

        for name, inc, rule in streams:
            if name == 'Group Fund Expenses':
                status_text = 'Deducted' if inc else 'Not Deducted'
                status_style = red_s if inc else label_s
            else:
                status_text = 'Included (Shared)' if inc else 'Retained (Accumulating)'
                status_style = green_s if inc else style(f'P_{name[:4]}', fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#7c3aed'), leading=11)
            policy_rows.append([
                Paragraph(name, cell_s),
                Paragraph(status_text, status_style),
                Paragraph(rule, cell_s),
            ])

        policy_table = Table(policy_rows, colWidths=[usable*0.30, usable*0.25, usable*0.45])
        policy_table.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), PRIMARY),
            ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
            ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, ALT_ROW]),
            ('GRID',          (0, 0), (-1, -1), 0.5, BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(policy_table)
        elements.append(Spacer(1, 4*mm))

        # ── Per-member distribution table ─────────────────────────
        elements.append(Paragraph('Per-Member Profit Distribution', section_s))

        dist_headers = [
            Paragraph('#', hdr_s),
            Paragraph('Member', hdr_s),
            Paragraph('Profit Share (KES)', hdr_s),
        ]
        dist_data = [dist_headers]

        for i, share in enumerate(interest_shares, 1):
            bg = colors.white if i % 2 == 1 else ALT_ROW
            dist_data.append([
                Paragraph(str(i), cell_s),
                Paragraph(share.member.name, cell_s),
                Paragraph(f'{share.amount:,.2f}', cell_s),
            ])

        # Totals row
        dist_data.append([
            Paragraph('', total_s),
            Paragraph('Total Profit Shared', total_s),
            Paragraph(f'KES {withdrawal.interest_shared:,.2f}', green_s),
        ])

        col_w = [usable*0.08, usable*0.60, usable*0.32]
        dist_table = Table(dist_data, colWidths=col_w, repeatRows=1)
        dist_table.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), PRIMARY),
            ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
            ('ROWBACKGROUNDS',(0, 1), (-1, -2), [colors.white, ALT_ROW]),
            ('BACKGROUND',    (0, -1), (-1, -1), GREEN_BG),
            ('GRID',          (0, 0), (-1, -1), 0.5, BORDER),
            ('LINEBELOW',     (0, 0), (-1, 0), 1.5, ACCENT),
            ('LINEABOVE',     (0, -1), (-1, -1), 1, ACCENT),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN',         (2, 0), (2, -1), 'RIGHT'),
        ]))
        elements.append(dist_table)
        elements.append(Spacer(1, 4*mm))

        # ── Member status table ───────────────────────────────────
        elements.append(Paragraph('Member Status', section_s))

        status_headers = [
            Paragraph('#', hdr_s),
            Paragraph('Member', hdr_s),
            Paragraph('Status', hdr_s),
        ]
        status_data = [status_headers]

        continuing = [ms for ms in member_statuses if ms.status == 'continuing']
        exiting    = [ms for ms in member_statuses if ms.status == 'exiting']

        for i, ms in enumerate(member_statuses, 1):
            status_label = 'Continuing' if ms.status == 'continuing' else 'Exiting'
            status_color = SUCCESS if ms.status == 'continuing' else TEXT_MUTED
            status_data.append([
                Paragraph(str(i), cell_s),
                Paragraph(ms.member.name, cell_s),
                Paragraph(status_label,
                          style(f'St{i}', fontSize=8, fontName='Helvetica-Bold',
                                textColor=status_color, leading=11)),
            ])

        # Summary footer row
        status_data.append([
            Paragraph('', total_s),
            Paragraph(f'Continuing: {len(continuing)}  |  Exiting: {len(exiting)}', total_s),
            Paragraph('', total_s),
        ])

        status_table = Table(status_data, colWidths=col_w, repeatRows=1)
        status_table.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), PRIMARY),
            ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
            ('ROWBACKGROUNDS',(0, 1), (-1, -2), [colors.white, ALT_ROW]),
            ('BACKGROUND',    (0, -1), (-1, -1), GREY_BG),
            ('GRID',          (0, 0), (-1, -1), 0.5, BORDER),
            ('LINEBELOW',     (0, 0), (-1, 0), 1.5, ACCENT),
            ('LINEABOVE',     (0, -1), (-1, -1), 1, BORDER),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(status_table)

        # ── Build PDF ─────────────────────────────────────────────
        doc.build(elements,
                  onFirstPage=page_footer,
                  onLaterPages=page_footer)

        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        return response


