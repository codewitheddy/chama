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


def _get_group_name():
    """Fetch the group name from SystemSetting, falling back to default."""
    try:
        from loans.models import SystemSetting
        return SystemSetting.get('group_name', 'Finance Wise TBM')
    except Exception:
        return 'Finance Wise TBM'


def _get_group_info():
    """Fetch full group info dict for PDF headers."""
    try:
        from loans.models import SystemSetting
        return SystemSetting.get_group_info()
    except Exception:
        return {'group_name': 'Finance Wise TBM', 'group_location': '', 'group_phone': ''}


IMMUTABLE_POWERED_BY = "Powered by Ropenix Investments Limited ( 018 218 0965 )"


def _get_document_footer(group_name=None):
    """Return immutable standard powered-by footer string for all generated documents."""
    name = group_name or _get_group_name()
    return f"{name} - {IMMUTABLE_POWERED_BY}"





# -- Brand colours -------------------------------------------------

PRIMARY   = colors.HexColor('#1e3a5f')   # dark navy

ACCENT    = colors.HexColor('#2563eb')   # blue

LIGHT_BG  = colors.HexColor('#f0f4ff')   # very light blue

ROW_EVEN  = colors.HexColor('#ffffff')

ROW_ODD   = colors.HexColor('#f8fafc')   # slate-50

ALT_ROW   = ROW_ODD

BORDER    = colors.HexColor('#e2e8f0')   # slate-200

TEXT_DARK = colors.HexColor('#1e293b')   # slate-800

TEXT_MUTED= colors.HexColor('#64748b')   # slate-500





def _sanitize_csv_cell(value):

    """Prevent spreadsheet formula injection for CSV exports."""

    text = '' if value is None else str(value).strip()

    if text and text[0] in ('=', '+', '-', '@', '\\t', '\\r'):

        return f"'{text}"

    return text





def draw_pdf_page_chrome(canvas, doc, title='', subtitle='', header_right_line1='', header_right_line2='', info=None, margin=1.5*cm):
    """
    Standard professional header (with group logo) and footer renderer for all PDF documents.
    Draws:
    1. Full-width colored header banner with dynamic theme palette.
    2. Group Logo image (if uploaded) with aspect-ratio preservation.
    3. Group Title / Custom PDF Title and Tagline / Subtitle.
    4. Right-side document metadata (e.g. Document Title, Date, Period, Member Name).
    5. Bottom footer bar with '[group name] - Powered by Ropenix Investments Limited ( 018 218 0965)' and page numbers.
    """
    import os
    from django.conf import settings
    from django.utils import timezone

    canvas.saveState()
    w, h = doc.pagesize
    if info is None:
        info = _get_group_info()

    # Set document metadata for browser tab titles and PDF readers
    group_title = info.get('pdf_header_title') or info.get('group_name') or 'Finance Wise TBM'
    display_title = title or subtitle or header_right_line1 or ''
    doc_meta_title = f"{group_title} - {display_title}" if display_title else group_title
    try:
        canvas.setTitle(doc_meta_title)
        canvas.setAuthor(group_title)
        canvas.setCreator(group_title)
        if display_title:
            canvas.setSubject(display_title)
    except Exception:
        pass

    # Dynamic primary color for header banner
    primary_hex = info.get('theme_primary_color') or '#1e2a3a'
    try:
        header_color = colors.HexColor(primary_hex)
    except Exception:
        header_color = PRIMARY

    # -- Top header bar --------------------------------------------
    canvas.setFillColor(header_color)
    canvas.rect(0, h - 28*mm, w, 28*mm, fill=1, stroke=0)

    # Check for group logo
    logo_drawn = False
    logo_url = info.get('group_logo', '')
    if logo_url and info.get('pdf_show_logo', True):
        rel = logo_url.lstrip('/')
        if rel.startswith('media/'):
            rel = rel[6:]
        logo_path = os.path.join(settings.MEDIA_ROOT, rel)
        if os.path.exists(logo_path):
            try:
                canvas.drawImage(
                    logo_path,
                    margin,
                    h - 24*mm,
                    width=20*mm,
                    height=20*mm,
                    preserveAspectRatio=True,
                    mask='auto'
                )
                logo_drawn = True
            except Exception:
                logo_drawn = False

    text_x = (margin + 24*mm) if logo_drawn else margin
    group_title = info.get('pdf_header_title') or info.get('group_name') or 'Finance Wise TBM'

    canvas.setFillColor(colors.white)
    canvas.setFont('Helvetica-Bold', 13)
    canvas.drawString(text_x, h - 13*mm, group_title)

    sub = subtitle or info.get('group_tagline', '')
    if sub:
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#cbd5e1'))
        canvas.drawString(text_x, h - 19*mm, str(sub))

    # Right side text
    canvas.setFillColor(colors.white)
    if header_right_line1:
        canvas.setFont('Helvetica-Bold', 9)
        canvas.drawRightString(w - margin, h - 13*mm, str(header_right_line1))
    elif title:
        canvas.setFont('Helvetica-Bold', 9)
        canvas.drawRightString(w - margin, h - 13*mm, str(title))

    if header_right_line2:
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#cbd5e1'))
        canvas.drawRightString(w - margin, h - 19*mm, str(header_right_line2))
    elif not header_right_line1 and not title:
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#cbd5e1'))
        canvas.drawRightString(w - margin, h - 19*mm, f'Generated: {timezone.localdate().strftime("%d %B %Y")}')

    # -- Bottom footer ---------------------------------------------
    canvas.setFillColor(BORDER)
    canvas.rect(0, 0, w, 10*mm, fill=1, stroke=0)

    canvas.setFillColor(TEXT_MUTED)
    canvas.setFont('Helvetica', 8)
    footer_text = _get_document_footer(info.get('group_name'))
    canvas.drawString(margin, 3.5*mm, footer_text)
    canvas.drawRightString(w - margin, 3.5*mm, f'Page {doc.page}')

    canvas.restoreState()


def _page_footer(canvas, doc, title='', orientation='portrait'):
    """Draws standard header (with logo) and footer bar on each PDF page."""
    draw_pdf_page_chrome(canvas, doc, title=title)





def export_csv(queryset, filename, fields, total_row=None):
    """
    Export queryset to CSV.
    fields: list of (field_name_or_callable, header_label)
    total_row: optional list of summary values appended as final row
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

    if total_row:
        writer.writerow([_sanitize_csv_cell(v) for v in total_row])

    return response


def export_pdf(queryset, filename, title, fields, orientation='portrait', summary_cards=None, total_row=None):
    """
    Export queryset to a styled A4 PDF.
    fields: list of (field_name_or_callable, header_label)
    summary_cards: list of (label, value) tuples or dicts to display in a top KPI metric ribbon
    total_row: list of strings/values matching the column count to append as a prominent table summary footer
    """
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'

    buffer = BytesIO()
    pagesize = landscape(A4) if orientation == 'landscape' else A4
    pw, ph = pagesize

    info = _get_group_info()
    group_title = info.get('pdf_header_title') or info.get('group_name') or 'Finance Wise TBM'
    doc_meta_title = f"{group_title} - {title}" if title else group_title

    # Margins: top leaves room for header bar (28mm), bottom for footer (10mm)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        title=doc_meta_title,
        author=group_title,
        subject=title or '',
        creator=group_title,
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

    # -- Report title block ----------------------------------------
    elements.append(Paragraph(title, title_style))
    elements.append(Paragraph(
        f'Report generated on {timezone.localdate().strftime("%d %B %Y")} &nbsp;|&nbsp; {queryset.count()} record(s)',
        subtitle_style
    ))
    elements.append(HRFlowable(width='100%', thickness=1, color=ACCENT, spaceAfter=4*mm))

    usable_width = pw - 3*cm   # left + right margins

    # -- Optional KPI Summary Cards Ribbon ------------------------
    if summary_cards:
        card_cells = []
        for item in summary_cards:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                lbl, val = str(item[0]), str(item[1])
            elif isinstance(item, dict):
                lbl, val = str(item.get('label', '')), str(item.get('value', ''))
            else:
                continue

            card_p = [
                Paragraph(f"<font size='7' color='#64748b'><b>{lbl.upper()}</b></font>", ParagraphStyle(
                    'CardLabel', parent=styles['Normal'], leading=9, spaceAfter=2
                )),
                Paragraph(f"<font size='10' color='#1e3a5f'><b>{val}</b></font>", ParagraphStyle(
                    'CardValue', parent=styles['Normal'], leading=12
                )),
            ]
            card_cells.append(card_p)

        if card_cells:
            card_count = len(card_cells)
            c_width = usable_width / card_count
            cards_table = Table([card_cells], colWidths=[c_width] * card_count)
            cards_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(cards_table)
            elements.append(Spacer(1, 4*mm))

    # -- Build table data ------------------------------------------
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

    has_total_row = bool(total_row)
    if has_total_row:
        t_row = []
        total_cell_style = ParagraphStyle(
            'TotalCell',
            parent=styles['Normal'],
            fontSize=8.5,
            fontName='Helvetica-Bold',
            textColor=PRIMARY,
            leading=11,
        )
        for val in total_row:
            t_row.append(Paragraph(f"<b>{val}</b>" if val else '', total_cell_style))
        data.append(t_row)

    # -- Column widths: distribute evenly -------------------------
    col_count = len(fields)
    col_width = usable_width / col_count

    table = Table(data, colWidths=[col_width] * col_count, repeatRows=1)

    # -- Table styling ---------------------------------------------
    table_styles = [
        # Header row
        ('BACKGROUND',   (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR',    (0, 0), (-1, 0), colors.white),
        ('TOPPADDING',   (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING',(0, 0), (-1, 0), 6),
        ('LEFTPADDING',  (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        # Grid
        ('GRID',         (0, 0), (-1, -1), 0.5, BORDER),
        ('LINEBELOW',    (0, 0), (-1, 0), 1.5, ACCENT),
        # Vertical alignment
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',   (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING',(0, 1), (-1, -1), 5),
    ]

    if has_total_row:
        # Non-total rows alternate backgrounds
        table_styles.append(('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, ALT_ROW]))
        # Total footer row styling
        table_styles.append(('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef2ff')))
        table_styles.append(('LINEABOVE', (0, -1), (-1, -1), 1.2, PRIMARY))
        table_styles.append(('LINEBELOW', (0, -1), (-1, -1), 1.2, PRIMARY))
        table_styles.append(('TOPPADDING', (0, -1), (-1, -1), 6))
        table_styles.append(('BOTTOMPADDING', (0, -1), (-1, -1), 6))
    else:
        table_styles.append(('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, ALT_ROW]))

    table.setStyle(TableStyle(table_styles))
    elements.append(table)

    # -- Build PDF -------------------------------------------------
    doc.build(
        elements,
        onFirstPage=lambda c, d: _page_footer(c, d, title),
        onLaterPages=lambda c, d: _page_footer(c, d, title),
    )

    pdf = buffer.getvalue()
    buffer.close()

    response.write(pdf)

    return response
