from django.utils import timezone
from datetime import timedelta


def group_settings(request):
    """Injects group profile info, branding, logo, and theme tokens into every template context."""
    try:
        from loans.models import SystemSetting
        return SystemSetting.get_group_info()
    except Exception:
        return {
            'group_name': 'Finance Wise TBM',
            'group_tagline': 'Table Banking Manager',
            'group_logo': '',
            'group_location': '',
            'group_phone': '',
            'group_email': '',
            'group_registration': '',
            'group_founded': '',
            'group_postal_address': '',
            'group_currency': 'KES',
            'theme_preset': 'navy_slate',
            'theme_sidebar_bg': '#1e2a3a',
            'theme_primary_color': '#2563eb',
            'theme_sidebar_hover': '#2c3e52',
            'theme_sidebar_text': '#94a3b8',
            'theme_sidebar_section': '#475569',
            'default_interest_rate': '10.00',
            'default_late_penalty_rate': '10.00',
            'grace_period_days': '0',
            'max_active_loans_per_member': '0',
            'savings_loan_multiplier': '0',
            'pdf_header_title': '',
            'pdf_footer_text': 'Finance Wise TBM - Powered by Ropenix Investments Limited ( 018 218 0965 )',
            'immutable_footer': 'Powered by Ropenix Investments Limited ( 018 218 0965 )',
            'pdf_show_logo': True,
            'pdf_show_contact': True,
        }


def pending_loan_applications(request):
    """Injects pending loan applications count for navigation badges."""
    try:
        from loans.models import LoanApplication
        return {'pending_applications_count': LoanApplication.objects.filter(status='pending').count()}
    except Exception:
        return {'pending_applications_count': 0}


def notification_count(request):
    """
    Injects total_alert_count into every template context.
    Used to show the bell badge in the topbar.
    """
    if not request.user.is_authenticated:
        return {}
    try:
        from loans.models import Loan, LoanApplication
        from penalties.models import Penalty
        from contributions.models import Contribution
        from members.models import Member

        today = timezone.localdate()

        late_count = Loan.objects.filter(status='late').count()
        due_soon   = Loan.objects.filter(
            status='active',
            due_date__gte=today,
            due_date__lte=today + timedelta(days=7),
        ).count()
        unpaid_pen = Penalty.objects.filter(paid=False).count()
        pending_apps = LoanApplication.objects.filter(status='pending').count()

        paid_ids   = Contribution.objects.filter(
            month=today.month, year=today.year
        ).values_list('member_id', flat=True)
        no_contrib = Member.objects.filter(is_active=True).exclude(id__in=paid_ids).count()

        total = late_count + due_soon + unpaid_pen + no_contrib + pending_apps
    except Exception:
        total = 0

    return {'total_alert_count': total}


def pending_transfers(request):
    if not request.user.is_authenticated:
        return {'pending_transfers_count': 0}
    try:
        from money_movement.models import MoneyTransfer
        return {'pending_transfers_count': MoneyTransfer.objects.filter(status=MoneyTransfer.STATUS_PENDING).count()}
    except Exception:
        return {'pending_transfers_count': 0}

