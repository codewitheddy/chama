import csv
from io import BytesIO
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable
)
from reportlab.platypus import PageTemplate, Frame
from reportlab.pdfgen import canvas as pdfcanvas
from django.utils import timezone


# ── Brand colours ─────────────────────────────────────────────────
PRIMARY   = colors.HexColor('#1e3a5f')   # dark navy
ACCENT    = colors.HexColor('#2563eb')   # blue
LIGHT_BG  = colors.HexColor('#f0f4ff')   # very light blue
ALT_ROW   = colors.HexColor('#f8fafc')   # near-white
BORDER    = colors.HexColor('#cbd5e1')   # slate-300
TEXT_DARK = colors.HexColor('#1e293b')
TEXT_MUTED= colors.HexColor('#64748b')


def _sanitize_csv_cell(value):
    """Prevent spreadsheet formula injection for CSV exports."""
    text = '' if value is None else str(value).strip()
    if text and text[0] in ('=', '+', '-', '@', '\\t', '\\r'):
        return f"'{text}"
    return text


def _page_footer(canvas, doc, title):
    """Draw header bar and footer on every page."""
    canvas.saveState()
    w, h = doc.pagesize

    # ── Top header bar ────────────────────────────────────────────
    canvas.setFillColor(PRIMARY)
    canvas.rect(0, h - 28*mm, w, 28*mm, fill=1, stroke=0)

    canvas.setFillColor(colors.white)
    canvas.setFont('Helvetica-Bold', 14)
    canvas.drawString(1.5*cm, h - 14*mm, 'DC Welfare Group')

    canvas.setFont('Helvetica', 9)
    canvas.drawRightString(w - 1.5*cm, h - 14*mm, title)

    # ── Bottom footer ─────────────────────────────────────────────
    canvas.setFillColor(BORDER)
    canvas.rect(0, 0, w, 10*mm, fill=1, stroke=0)

    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont('Helvetica', 8)
    canvas.drawString(1.5*cm, 3.5*mm, f'Generated: {timezone.localdate().strftime("%d %B %Y")}')
    canvas.drawRightString(w - 1.5*cm, 3.5*mm,
                           f'Page {doc.page}')

    canvas.restoreState()


def export_csv(queryset, filename, fields):
    """
    Export queryset to CSV.
    fields: list of (field_name_or_callable, header_label)
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'

    writer = csv.writer(response)
    writer.writerow([label for _, label in fields])

    for obj in queryset:
        row = []
        for field_name, _ in fields:
            if callable(field_name):
                value = field_name(obj)
            elif '.' in str(field_name):
                parts = field_name.split('.')
                value = obj
                for part in parts:
                    value = getattr(value, part, '') or ''
            else:
                value = getattr(obj, field_name, '')
            row.append(_sanitize_csv_cell(value))
        writer.writerow(row)

    return response


def export_pdf(queryset, filename, title, fields, orientation='portrait'):
    """
    Export queryset to a styled A4 PDF.
    fields: list of (field_name_or_callable, header_label)
    """
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'

    buffer = BytesIO()
    pagesize = landscape(A4) if orientation == 'landscape' else A4
    pw, ph = pagesize

    # Margins: top leaves room for header bar (28mm), bottom for footer (10mm)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        topMargin=32*mm,
        bottomMargin=16*mm,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Normal'],
        fontSize=16,
        fontName='Helvetica-Bold',
        textColor=PRIMARY,
        spaceAfter=2*mm,
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=9,
        fontName='Helvetica',
        textColor=TEXT_MUTED,
        spaceAfter=4*mm,
    )
    cell_style = ParagraphStyle(
        'Cell',
        parent=styles['Normal'],
        fontSize=8,
        fontName='Helvetica',
        textColor=TEXT_DARK,
        leading=11,
    )

    elements = []

    # ── Report title block ────────────────────────────────────────
    elements.append(Paragraph(title, title_style))
    elements.append(Paragraph(
        f'Report generated on {timezone.localdate().strftime("%d %B %Y")} &nbsp;|&nbsp; {queryset.count()} record(s)',
        subtitle_style
    ))
    elements.append(HRFlowable(width='100%', thickness=1, color=ACCENT, spaceAfter=4*mm))

    # ── Build table data ──────────────────────────────────────────
    headers = [Paragraph(f'<b>{label}</b>', ParagraphStyle(
        'Header', parent=styles['Normal'],
        fontSize=8, fontName='Helvetica-Bold',
        textColor=colors.white, leading=11,
    )) for _, label in fields]

    data = [headers]

    for obj in queryset:
        row = []
        for field_name, _ in fields:
            if callable(field_name):
                value = field_name(obj)
            elif '.' in str(field_name):
                parts = field_name.split('.')
                value = obj
                for part in parts:
                    value = getattr(value, part, '') or ''
            else:
                value = getattr(obj, field_name, '')
            row.append(Paragraph(str(value) if value is not None else '—', cell_style))
        data.append(row)

    # ── Column widths: distribute evenly ─────────────────────────
    usable_width = pw - 3*cm   # left + right margins
    col_count = len(fields)
    col_width = usable_width / col_count

    table = Table(data, colWidths=[col_width] * col_count, repeatRows=1)

    # ── Table styling ─────────────────────────────────────────────
    style = TableStyle([
        # Header row
        ('BACKGROUND',   (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR',    (0, 0), (-1, 0), colors.white),
        ('TOPPADDING',   (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING',(0, 0), (-1, 0), 6),
        ('LEFTPADDING',  (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        # Alternating rows
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ALT_ROW]),
        # Grid
        ('GRID',         (0, 0), (-1, -1), 0.5, BORDER),
        ('LINEBELOW',    (0, 0), (-1, 0), 1.5, ACCENT),
        # Vertical alignment
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',   (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING',(0, 1), (-1, -1), 5),
    ])
    table.setStyle(style)

    elements.append(table)

    # ── Build PDF ─────────────────────────────────────────────────
    doc.build(
        elements,
        onFirstPage=lambda c, d: _page_footer(c, d, title),
        onLaterPages=lambda c, d: _page_footer(c, d, title),
    )

    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    return response