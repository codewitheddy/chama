from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import (
    TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView,
)
from django.views import View
from django.urls import reverse_lazy, reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Sum, Q
from django.core.paginator import Paginator
from decimal import Decimal
from datetime import date

from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin, MemberAccessMixin, AdminPasswordDeleteMixin
from members.models import Member
from utils.exports import export_csv, export_pdf
from utils.exports import _get_group_name, _get_document_footer, draw_pdf_page_chrome
from utils.payment_type_mixin import PAYMENT_TYPE_CHOICES
from django.utils import timezone

from .models import (
    WelfareContributionRate, WelfareContribution, WelfareEvent,
    WelfareDisbursement, WelfareSupportContribution, WelfareExternalSupport,
    get_welfare_balance, MONTH_CHOICES,
)
from .forms import (
    WelfareContributionRateForm, WelfareContributionForm, WelfareEventForm,
    WelfareDisbursementForm, WelfareSupportContributionForm,
    WelfareExternalSupportForm,
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
        from bank_accounts.models import BankAccount
        welfare_banks = list(BankAccount.objects.filter(is_active=True, fund_type=BankAccount.FUND_TYPE_WELFARE).prefetch_related('balances'))
        welfare_bank_total = sum(b.current_balance for b in welfare_banks)
        ctx['welfare_bank_accounts'] = welfare_banks
        ctx['welfare_bank_balance'] = welfare_bank_total
        ctx['current_rate'] = WelfareContributionRate.current_rate()
        return ctx


# ── Contribution Rate ─────────────────────────────────────────────

class WelfareContributionRateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = WelfareContributionRate
    form_class = WelfareContributionRateForm
    template_name = 'welfare/rate_form.html'
    success_url = reverse_lazy('welfare:rate')
    success_message = "Monthly contribution rate updated."

    def get_initial(self):
        initial = super().get_initial()
        initial['effective_date'] = timezone.localdate()
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['current_rate'] = WelfareContributionRate.current_rate()
        ctx['rate_history'] = WelfareContributionRate.objects.order_by('-effective_date')
        ctx['today'] = timezone.localdate()
        ctx['is_editing'] = False
        return ctx


class WelfareContributionRateUpdateView(AdminRequiredMixin, SuccessMessageMixin, UpdateView):
    model = WelfareContributionRate
    form_class = WelfareContributionRateForm
    template_name = 'welfare/rate_form.html'
    success_url = reverse_lazy('welfare:rate')
    success_message = "Monthly contribution rate updated successfully."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['current_rate'] = WelfareContributionRate.current_rate()
        ctx['rate_history'] = WelfareContributionRate.objects.order_by('-effective_date')
        ctx['today'] = timezone.localdate()
        ctx['is_editing'] = True
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        password = request.POST.get('admin_password', '').strip()

        if not password:
            form = self.get_form()
            ctx = self.get_context_data(
                form=form,
                password_error="Admin password is required to update contribution rates."
            )
            return self.render_to_response(ctx)

        if not request.user.check_password(password):
            form = self.get_form()
            ctx = self.get_context_data(
                form=form,
                password_error="Incorrect password. Rate update cancelled."
            )
            return self.render_to_response(ctx)

        return super().post(request, *args, **kwargs)


class WelfareContributionRateDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = WelfareContributionRate
    template_name = 'welfare/rate_confirm_delete.html'
    success_url = reverse_lazy('welfare:rate')

    def delete(self, request, *args, **kwargs):
        response = super().delete(request, *args, **kwargs)
        messages.success(request, "Monthly contribution rate deleted successfully.")
        return response


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
        q = self.request.GET.get('q', '').strip()
        month = self.request.GET.get('month', '').strip()
        year = self.request.GET.get('year', '').strip()

        ctx['q'] = q
        ctx['selected_month'] = month
        ctx['selected_year'] = year
        ctx['months'] = [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)]
        ctx['years'] = range(today.year - 3, today.year + 1)

        qs = self.get_queryset()
        ctx['total_count'] = qs.count()
        ctx['filtered_count'] = qs.count()
        ctx['filtered_total'] = qs.aggregate(t=Sum('amount'))['t'] or 0

        labels = []
        if q:
            labels.append(f'"{q}"')
        if month:
            try:
                labels.append(date(2000, int(month), 1).strftime('%B'))
            except (ValueError, TypeError):
                pass
        if year:
            labels.append(str(year))
        ctx['filter_label'] = ' / '.join(labels) if labels else 'Filtered'

        # Stats — always from full dataset, not filtered
        ctx['stat_total_contributions'] = (
            WelfareContribution.objects.aggregate(t=Sum('amount'))['t'] or 0
        )
        ctx['stat_total_disbursed'] = (
            WelfareDisbursement.objects.aggregate(t=Sum('amount'))['t'] or 0
        )
        ctx['stat_welfare_balance'] = get_welfare_balance()
        ctx['stat_open_events'] = WelfareEvent.objects.filter(status='open').count()

        # Dedicated Welfare Bank Account details
        from bank_accounts.models import BankAccount
        welfare_banks = list(BankAccount.objects.filter(is_active=True, fund_type=BankAccount.FUND_TYPE_WELFARE).prefetch_related('balances'))
        welfare_bank_total = sum(b.current_balance for b in welfare_banks)
        ctx['welfare_bank_accounts'] = welfare_banks
        ctx['welfare_bank_balance'] = welfare_bank_total
        ctx['primary_welfare_bank'] = welfare_banks[0] if welfare_banks else None

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
        return self._export(request)

    def post(self, request):
        return self._export(request)

    def _export(self, request):
        fmt = request.GET.get('format') or request.POST.get('format', 'csv')
        qs = WelfareContribution.objects.select_related('member').order_by('-date')

        # Check for explicitly selected IDs (from bulk selection)
        raw_ids = request.GET.get('ids') or request.POST.get('ids', '')
        if raw_ids:
            id_list = [int(i) for i in raw_ids.split(',') if i.strip().isdigit()]
            if id_list:
                qs = qs.filter(pk__in=id_list)
        else:
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

        total_amount = qs.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        total_count = qs.count()

        summary_cards = [
            ('Total Records', f'{total_count:,}'),
            ('Total Welfare', f'KES {total_amount:,.2f}'),
        ]
        if not raw_ids:
            if month:
                from welfare.models import MONTH_CHOICES
                m_dict = dict(MONTH_CHOICES)
                m_label = m_dict.get(int(month), month) if str(month).isdigit() else month
                summary_cards.append(('Month', str(m_label)))
            if year:
                summary_cards.append(('Year', str(year)))
            if q:
                summary_cards.append(('Member Search', str(q)))

        total_row = [
            'TOTAL SUMMARY',
            '',
            '',
            f'KES {total_amount:,.2f}',
            '',
            '',
            '',
        ]

        title = 'Selected Welfare Contributions Report' if raw_ids else 'Welfare Contributions Report'
        if fmt == 'pdf':
            return export_pdf(qs, 'welfare_contributions', title, fields, orientation='landscape', summary_cards=summary_cards, total_row=total_row)
        return export_csv(qs, 'welfare_contributions', fields, total_row=total_row)


class WelfareBulkContributionDeleteView(AdminRequiredMixin, View):
    """Bulk delete multiple welfare contributions (requires admin password)."""

    def post(self, request):
        raw_ids = request.POST.get('contribution_ids', '')
        contribution_ids = [int(id) for id in raw_ids.split(',') if id.strip().isdigit()]

        if not contribution_ids:
            messages.error(request, "No welfare contributions selected.")
            return redirect('welfare:contribution_list')

        contributions = WelfareContribution.objects.filter(pk__in=contribution_ids).select_related('member')
        if not contributions.exists():
            messages.error(request, "Selected welfare contributions no longer exist.")
            return redirect('welfare:contribution_list')

        total_amount = sum(c.amount for c in contributions)

        if request.POST.get('confirm') == 'true':
            password = request.POST.get('admin_password', '')
            reason = request.POST.get('delete_reason', '').strip()

            if not reason:
                return render(request, 'welfare/bulk_delete_confirm.html', {
                    'contributions': contributions,
                    'total_amount': total_amount,
                    'error': 'A reason for deletion is required.',
                    'contribution_ids': ','.join(str(id) for id in contribution_ids),
                    'delete_reason': reason,
                })

            if not request.user.check_password(password):
                return render(request, 'welfare/bulk_delete_confirm.html', {
                    'contributions': contributions,
                    'total_amount': total_amount,
                    'error': 'Incorrect password. Deletion cancelled.',
                    'contribution_ids': ','.join(str(id) for id in contribution_ids),
                    'delete_reason': reason,
                })

            from recycle_bin.models import DeletedRecord
            from recycle_bin.serializer import serialize_instance

            deleted_count = 0
            with transaction.atomic():
                for contrib in contributions:
                    try:
                        data = serialize_instance(contrib)
                        DeletedRecord.objects.create(
                            app_label=contrib._meta.app_label,
                            model_name=contrib._meta.model_name,
                            object_id=str(contrib.pk),
                            object_repr=str(contrib)[:300],
                            data=data,
                            delete_reason=reason,
                            deleted_by=request.user,
                        )
                        contrib.delete()
                        deleted_count += 1
                    except Exception as e:
                        messages.error(request, f"Error deleting record #{contrib.pk}: {str(e)[:60]}")

            if deleted_count:
                messages.success(request, f"{deleted_count} welfare contribution(s) deleted successfully.")
            return redirect('welfare:contribution_list')

        return render(request, 'welfare/bulk_delete_confirm.html', {
            'contributions': contributions,
            'total_amount': total_amount,
            'contribution_ids': ','.join(str(id) for id in contribution_ids),
        })


class WelfareBulkContributionUpdateView(TreasurerRequiredMixin, View):
    """Bulk update fields (month, year, payment method) for selected welfare contributions."""

    def post(self, request):
        raw_ids = request.POST.get('contribution_ids', '')
        contribution_ids = [int(id) for id in raw_ids.split(',') if id.strip().isdigit()]

        if not contribution_ids:
            messages.error(request, "No welfare contributions selected.")
            return redirect('welfare:contribution_list')

        contributions = WelfareContribution.objects.filter(pk__in=contribution_ids)
        if not contributions.exists():
            messages.error(request, "Selected welfare contributions no longer exist.")
            return redirect('welfare:contribution_list')

        new_month = request.POST.get('bulk_month', '').strip()
        new_year = request.POST.get('bulk_year', '').strip()
        new_payment_type = request.POST.get('bulk_payment_type', '').strip()

        updates = {}
        if new_month:
            try:
                m_val = int(new_month)
                if 1 <= m_val <= 12:
                    updates['month'] = m_val
            except ValueError:
                pass

        if new_year:
            try:
                y_val = int(new_year)
                if 2000 <= y_val <= 2100:
                    updates['year'] = y_val
            except ValueError:
                pass

        if new_payment_type and new_payment_type in dict(PAYMENT_TYPE_CHOICES):
            updates['payment_type'] = new_payment_type
            if new_payment_type != 'mpesa':
                updates['mpesa_code'] = ''

        if not updates:
            messages.info(request, "No update fields were specified.")
            return redirect('welfare:contribution_list')

        with transaction.atomic():
            updated_count = 0
            for contrib in contributions:
                for field, val in updates.items():
                    setattr(contrib, field, val)
                contrib.save()
                updated_count += 1

        messages.success(request, f"{updated_count} welfare contribution(s) updated successfully.")
        return redirect('welfare:contribution_list')


# ── Defaulters ────────────────────────────────────────────────────

class WelfareBulkContributionView(TreasurerRequiredMixin, View):
    template_name = 'welfare/bulk_contribution.html'

    def _get_context(self, request, post_data=None):
        from decimal import Decimal
        today = timezone.localdate()

        default_date   = post_data.get('default_date', str(today)) if post_data else str(today)
        default_amount = post_data.get('default_amount', '') if post_data else ''
        default_method = post_data.get('default_method', 'cash') if post_data else 'cash'
        selected_month = int(post_data.get('month', today.month)) if post_data else today.month
        selected_year  = int(post_data.get('year',  today.year))  if post_data else today.year

        # Pre-fill default_amount from the configured rate if not set
        rate = WelfareContributionRate.rate_for_period(selected_year, selected_month)
        if not default_amount and rate:
            default_amount = str(rate.amount)

        already_paid_ids = set(
            WelfareContribution.objects.filter(month=selected_month, year=selected_year)
            .values_list('member_id', flat=True)
        )

        members = list(Member.objects.filter(is_active=True).order_by('name'))
        rows = []
        for m in members:
            prefix = f'member_{m.pk}'
            already_paid = m.pk in already_paid_ids
            if post_data:
                skip      = post_data.get(f'{prefix}_skip') == '1'
                amount    = post_data.get(f'{prefix}_amount', '').strip()
                pdate     = post_data.get(f'{prefix}_date', '').strip()
                ptype     = post_data.get(f'{prefix}_payment_type', 'cash')
                mcode     = post_data.get(f'{prefix}_mpesa_code', '').strip().upper()
                row_error = post_data.get(f'_err_{m.pk}', '')
            else:
                skip      = already_paid
                amount    = default_amount
                pdate     = default_date
                ptype     = default_method
                mcode     = ''
                row_error = ''

            rows.append({
                'member':       m,
                'prefix':       prefix,
                'already_paid': already_paid,
                'skip':         skip,
                'amount':       amount,
                'date':         pdate,
                'payment_type': ptype,
                'mpesa_code':   mcode,
                'error':        row_error,
            })

        months = [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)]
        years  = range(today.year - 2, today.year + 2)

        return {
            'rows':               rows,
            'default_date':       default_date,
            'default_amount':     default_amount,
            'default_method':     default_method,
            'selected_month':     selected_month,
            'selected_year':      selected_year,
            'months':             months,
            'years':              years,
            'already_paid_count': len(already_paid_ids),
            'current_rate':       rate,
        }

    def get(self, request):
        return render(request, self.template_name, self._get_context(request))

    def post(self, request):
        import re
        from decimal import Decimal, InvalidOperation
        from datetime import datetime as dt

        post = request.POST
        selected_month = int(post.get('month', timezone.localdate().month))
        selected_year  = int(post.get('year',  timezone.localdate().year))

        members = list(Member.objects.filter(is_active=True).order_by('name'))

        already_paid_ids = set(
            WelfareContribution.objects.filter(month=selected_month, year=selected_year)
            .values_list('member_id', flat=True)
        )

        rate = WelfareContributionRate.rate_for_period(selected_year, selected_month)

        to_save = []
        errors  = {}
        skipped = 0

        for m in members:
            prefix = f'member_{m.pk}'
            skip = post.get(f'{prefix}_skip') == '1' or m.pk in already_paid_ids
            if skip:
                skipped += 1
                continue

            amount_str = post.get(f'{prefix}_amount', '').strip()
            pdate_str  = post.get(f'{prefix}_date',   '').strip()
            ptype      = post.get(f'{prefix}_payment_type', 'cash')
            mcode      = post.get(f'{prefix}_mpesa_code',  '').strip().upper()

            # Amount
            try:
                amount = Decimal(amount_str)
                if amount <= 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                errors[m.pk] = 'Enter a valid amount greater than zero.'
                continue

            # Validate against configured rate
            if rate and amount != rate.amount:
                errors[m.pk] = (
                    f'Amount must be exactly KES {rate.amount:,.2f} '
                    f'(the rate for this period).'
                )
                continue

            # Date
            try:
                pdate = dt.strptime(pdate_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                errors[m.pk] = 'Enter a valid date.'
                continue

            # M-Pesa code
            if ptype == 'mpesa':
                if not mcode:
                    errors[m.pk] = 'M-Pesa confirmation code is required.'
                    continue
                if not re.match(r'^[A-Za-z0-9]{6,20}$', mcode):
                    errors[m.pk] = 'Invalid M-Pesa code (6–20 alphanumeric characters).'
                    continue
            else:
                mcode = ''

            to_save.append({
                'member':       m,
                'amount':       amount,
                'date':         pdate,
                'month':        pdate.month,
                'year':         pdate.year,
                'payment_type': ptype,
                'mpesa_code':   mcode,
            })

        if errors:
            mutable = post.copy()
            for pk, msg in errors.items():
                mutable[f'_err_{pk}'] = msg
            ctx = self._get_context(request, mutable)
            ctx['selected_month'] = selected_month
            ctx['selected_year']  = selected_year
            messages.error(request, f'{len(errors)} row(s) have errors. Please fix them below.')
            return render(request, self.template_name, ctx)

        if not to_save:
            messages.warning(request, 'No contributions to record — all rows were skipped.')
            return redirect('welfare:bulk')

        with transaction.atomic():
            created = []
            for row in to_save:
                c = WelfareContribution.objects.create(
                    member       = row['member'],
                    amount       = row['amount'],
                    date         = row['date'],
                    month        = row['month'],
                    year         = row['year'],
                    payment_type = row['payment_type'],
                    mpesa_code   = row['mpesa_code'],
                )
                created.append(c)

        messages.success(
            request,
            f'{len(created)} welfare contribution(s) recorded successfully.'
            + (f' {skipped} skipped.' if skipped else '')
        )
        return redirect('welfare:contribution_list')



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
    paginate_by = 10

    def get_paginate_by(self, queryset):
        per_page = self.request.GET.get('per_page')
        if per_page:
            try:
                per_page_int = int(per_page)
                if per_page_int in [5, 10, 20, 50, 100]:
                    return per_page_int
            except (ValueError, TypeError):
                pass
        return 10

    def get_queryset(self):
        qs = WelfareEvent.objects.select_related('beneficiary')
        q = self.request.GET.get('q', '').strip()
        status = self.request.GET.get('status', '').strip()
        year = self.request.GET.get('year', '').strip()
        sort = self.request.GET.get('sort', '-date_opened').strip()

        if q:
            qs = qs.filter(
                Q(beneficiary__name__icontains=q) |
                Q(beneficiary__phone__icontains=q) |
                Q(description__icontains=q)
            )
        if status in ['open', 'closed']:
            qs = qs.filter(status=status)
        if year:
            try:
                qs = qs.filter(date_opened__year=int(year))
            except (ValueError, TypeError):
                pass

        if sort == 'date_asc':
            qs = qs.order_by('date_opened', 'pk')
        elif sort == 'beneficiary':
            qs = qs.order_by('beneficiary__name')
        elif sort == 'beneficiary_desc':
            qs = qs.order_by('-beneficiary__name')
        else:
            qs = qs.order_by('-date_opened', '-pk')

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        all_events = WelfareEvent.objects.all()

        # Query and filter state
        ctx['q'] = self.request.GET.get('q', '')
        ctx['current_status'] = self.request.GET.get('status', '')
        ctx['selected_year'] = self.request.GET.get('year', '')
        ctx['selected_sort'] = self.request.GET.get('sort', '-date_opened')
        ctx['selected_per_page'] = str(self.get_paginate_by(self.object_list))

        # Stats
        ctx['stat_total_events'] = all_events.count()
        ctx['stat_open_events'] = all_events.filter(status='open').count()
        ctx['stat_closed_events'] = all_events.filter(status='closed').count()
        ctx['stat_welfare_balance'] = get_welfare_balance()

        total_disb = WelfareDisbursement.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        total_supp = WelfareSupportContribution.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        total_ext  = WelfareExternalSupport.objects.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        ctx['stat_total_mobilized'] = total_disb + total_supp + total_ext
        ctx['stat_total_disbursed'] = total_disb

        # Distinct years
        years_qs = WelfareEvent.objects.dates('date_opened', 'year', order='DESC')
        ctx['years'] = [d.year for d in years_qs]

        # Elided page range for clean, accessible pagination
        page_obj = ctx.get('page_obj')
        paginator = ctx.get('paginator')
        if page_obj and paginator and paginator.num_pages > 1:
            try:
                ctx['page_range'] = paginator.get_elided_page_range(
                    number=page_obj.number,
                    on_each_side=2,
                    on_ends=1,
                )
            except Exception:
                ctx['page_range'] = paginator.page_range
        elif paginator:
            ctx['page_range'] = paginator.page_range

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

        # Member support contributions with pagination (10 per page)
        support_qs = event.support_contributions.select_related('contributor').order_by('-date', '-pk')
        support_paginator = Paginator(support_qs, 10)
        support_page_num = self.request.GET.get('support_page', 1)
        support_page_obj = support_paginator.get_page(support_page_num)
        ctx['support_contributions'] = support_page_obj
        ctx['support_page_obj'] = support_page_obj
        ctx['support_paginator'] = support_paginator
        ctx['support_total_count'] = support_qs.count()
        ctx['support_total'] = event.support_total
        if support_paginator.num_pages > 1:
            try:
                ctx['support_page_range'] = support_paginator.get_elided_page_range(
                    number=support_page_obj.number, on_each_side=1, on_ends=1
                )
            except Exception:
                ctx['support_page_range'] = support_paginator.page_range
        else:
            ctx['support_page_range'] = support_paginator.page_range

        # External support with pagination (10 per page)
        ext_qs = event.external_support.order_by('-date', '-pk')
        ext_paginator = Paginator(ext_qs, 10)
        ext_page_num = self.request.GET.get('ext_page', 1)
        ext_page_obj = ext_paginator.get_page(ext_page_num)
        ctx['external_support'] = ext_page_obj
        ctx['ext_page_obj'] = ext_page_obj
        ctx['ext_paginator'] = ext_paginator
        ctx['external_total_count'] = ext_qs.count()
        ctx['external_support_total'] = event.external_support_total
        if ext_paginator.num_pages > 1:
            try:
                ctx['ext_page_range'] = ext_paginator.get_elided_page_range(
                    number=ext_page_obj.number, on_each_side=1, on_ends=1
                )
            except Exception:
                ctx['ext_page_range'] = ext_paginator.page_range
        else:
            ctx['ext_page_range'] = ext_paginator.page_range

        ctx['event_total'] = event.event_total

        # Funding breakdown percentages for visual metrics
        total = event.event_total
        if total and total > Decimal('0'):
            ctx['pct_disbursed'] = round(float((event.disbursement_amount / total) * 100), 1)
            ctx['pct_support'] = round(float((event.support_total / total) * 100), 1)
            ctx['pct_external'] = round(float((event.external_support_total / total) * 100), 1)
        else:
            ctx['pct_disbursed'] = 0.0
            ctx['pct_support'] = 0.0
            ctx['pct_external'] = 0.0

        return ctx


class WelfareEventCloseView(TreasurerRequiredMixin, View):
    def post(self, request, pk):
        event = get_object_or_404(WelfareEvent, pk=pk)
        event.status = 'closed'
        event.save()
        messages.success(request, f'Welfare event for {event.beneficiary.name} has been closed.')
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('welfare:event_detail', kwargs={'pk': pk})
        return redirect(next_url)


class WelfareEventReopenView(TreasurerRequiredMixin, View):
    def post(self, request, pk):
        event = get_object_or_404(WelfareEvent, pk=pk)
        event.status = 'open'
        event.save()
        messages.success(request, f'Welfare event for {event.beneficiary.name} has been reopened.')
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('welfare:event_detail', kwargs={'pk': pk})
        return redirect(next_url)


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


# ── External (Non-Member) Support ────────────────────────────────

class WelfareExternalSupportCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = WelfareExternalSupport
    form_class = WelfareExternalSupportForm
    template_name = 'welfare/external_support_form.html'
    success_message = "External support recorded."

    def get_event(self):
        return get_object_or_404(WelfareEvent, pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['event'] = self.get_event()
        return ctx

    def form_valid(self, form):
        form.instance.event = self.get_event()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('welfare:event_detail', kwargs={'pk': self.kwargs['pk']})


class WelfareExternalSupportUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = WelfareExternalSupport
    form_class = WelfareExternalSupportForm
    template_name = 'welfare/external_support_form.html'
    success_message = "External support updated."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['event'] = self.object.event
        return ctx

    def get_success_url(self):
        return reverse('welfare:event_detail', kwargs={'pk': self.object.event_id})


class WelfareExternalSupportDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = WelfareExternalSupport
    template_name = 'welfare/external_support_confirm_delete.html'

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
        external_qs = event.external_support.order_by('-date')

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
            draw_pdf_page_chrome(canvas, d, subtitle='Welfare Event Summary', header_right_line1=event.beneficiary.name, header_right_line2=f'Generated: {dt.today().strftime("%d %B %Y")}')

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

        # External (non-member) support
        elements.append(Paragraph('External Support (Non-Members)', section_s))
        if external_qs.exists():
            ext_data = [
                [Paragraph('<b>SUPPORTER</b>', hdr_s), Paragraph('<b>PHONE</b>', hdr_s),
                 Paragraph('<b>AMOUNT</b>', hdr_r), Paragraph('<b>DATE</b>', hdr_s),
                 Paragraph('<b>NOTES</b>', hdr_s)],
            ]
            for es in external_qs:
                ext_data.append([
                    Paragraph(es.supporter_name, cell_s),
                    Paragraph(es.supporter_phone or '—', muted_s),
                    kes(es.amount),
                    Paragraph(str(es.date), cell_s),
                    Paragraph(es.notes or '—', muted_s),
                ])
            elements.append(make_table(ext_data, [0.25, 0.18, 0.20, 0.17, 0.20]))
        else:
            elements.append(Paragraph('No external support recorded.', muted_s))

        # Event total
        elements.append(Spacer(1, 6*mm))
        total_data = [
            [Paragraph('<b>SOURCE</b>', hdr_s), Paragraph('<b>AMOUNT</b>', hdr_r)],
            [Paragraph('Welfare Fund Disbursement', cell_s),
             kes(event.disbursement_amount)],
            [Paragraph('Member Support Contributions', cell_s),
             kes(event.support_total)],
            [Paragraph('External Support (Non-Members)', cell_s),
             kes(event.external_support_total)],
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



