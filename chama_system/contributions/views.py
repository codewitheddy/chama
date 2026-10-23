from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
from django.views import View
from django.urls import reverse_lazy
from django.db.models import Q, Sum
from decimal import Decimal
from django.db import transaction
from django.contrib import messages
from django.shortcuts import render, redirect
from .models import Contribution
from .forms import ContributionForm
from members.models import Member
from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin, MemberAccessMixin, AdminPasswordDeleteMixin
from utils.exports import export_csv, export_pdf
from utils.payment_type_mixin import PAYMENT_TYPE_CHOICES
from datetime import date
from django.utils import timezone


class ContributionListView(MemberAccessMixin, ListView):
    model = Contribution
    template_name = 'contributions/contribution_list.html'
    context_object_name = 'contributions'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('member')
        q = self.request.GET.get('q', '').strip()
        month = self.request.GET.get('month', '').strip()
        year = self.request.GET.get('year', '').strip()
        payment_type = self.request.GET.get('payment_type', '').strip()
        if q:
            qs = qs.filter(member__name__icontains=q)
        if month:
            qs = qs.filter(month=month)
        if year:
            qs = qs.filter(year=year)
        if payment_type:
            qs = qs.filter(payment_type=payment_type)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_month'] = self.request.GET.get('month', '')
        ctx['selected_year'] = self.request.GET.get('year', '')
        ctx['selected_payment_type'] = self.request.GET.get('payment_type', '')
        ctx['payment_type_choices'] = PAYMENT_TYPE_CHOICES
        ctx['months'] = [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)]
        ctx['years'] = range(today.year - 3, today.year + 1)

        from django.db.models import Sum, Count
        all_contribs = Contribution.objects.all()

        # Grand Overall Totals & Method Breakdown (Fixed across whole chama)
        grand_total = all_contribs.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        grand_count = all_contribs.count()
        grand_cash_total = all_contribs.filter(payment_type='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        grand_cash_count = all_contribs.filter(payment_type='cash').count()
        grand_mpesa_total = all_contribs.filter(payment_type='mpesa').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        grand_mpesa_count = all_contribs.filter(payment_type='mpesa').count()

        ctx['grand_total'] = grand_total
        ctx['grand_count'] = grand_count
        ctx['grand_cash_total'] = grand_cash_total
        ctx['grand_cash_count'] = grand_cash_count
        ctx['grand_mpesa_total'] = grand_mpesa_total
        ctx['grand_mpesa_count'] = grand_mpesa_count
        ctx['grand_cash_pct'] = round(float((grand_cash_total / grand_total) * 100), 1) if grand_total > 0 else 0
        ctx['grand_mpesa_pct'] = round(float((grand_mpesa_total / grand_total) * 100), 1) if grand_total > 0 else 0

        # Filtered Totals & Method Breakdown (Matches current filter parameters)
        filtered_qs = self.get_queryset()
        filtered_total = filtered_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        filtered_count = filtered_qs.count()
        filtered_cash_total = filtered_qs.filter(payment_type='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        filtered_cash_count = filtered_qs.filter(payment_type='cash').count()
        filtered_mpesa_total = filtered_qs.filter(payment_type='mpesa').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        filtered_mpesa_count = filtered_qs.filter(payment_type='mpesa').count()

        ctx['filtered_total'] = filtered_total
        ctx['filtered_count'] = filtered_count
        ctx['filtered_cash_total'] = filtered_cash_total
        ctx['filtered_cash_count'] = filtered_cash_count
        ctx['filtered_mpesa_total'] = filtered_mpesa_total
        ctx['filtered_mpesa_count'] = filtered_mpesa_count
        ctx['filtered_cash_pct'] = round(float((filtered_cash_total / filtered_total) * 100), 1) if filtered_total > 0 else 0
        ctx['filtered_mpesa_pct'] = round(float((filtered_mpesa_total / filtered_total) * 100), 1) if filtered_total > 0 else 0

        # Label for the filtered total card
        month_val = self.request.GET.get('month', '')
        year_val = self.request.GET.get('year', '')
        pt_val = self.request.GET.get('payment_type', '')
        labels = []
        if month_val:
            try:
                labels.append(date(2000, int(month_val), 1).strftime('%B'))
            except (ValueError, TypeError):
                pass
        if year_val:
            labels.append(str(year_val))
        if pt_val:
            labels.append(dict(PAYMENT_TYPE_CHOICES).get(pt_val, pt_val.upper()))

        ctx['filter_label'] = ' · '.join(labels) if labels else 'Filtered'

        return ctx


class ContributionCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = Contribution
    form_class = ContributionForm
    template_name = 'contributions/contribution_form.html'
    success_url = reverse_lazy('contributions:add')
    success_message = "Contribution recorded. Add another below."


class ContributionUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Contribution
    form_class = ContributionForm
    template_name = 'contributions/contribution_form.html'
    success_url = reverse_lazy('contributions:list')
    success_message = "Contribution updated."


class ContributionDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = Contribution
    template_name = 'contributions/contribution_confirm_delete.html'
    success_url = reverse_lazy('contributions:list')


class ContributionDefaultersView(MemberAccessMixin, TemplateView):
    template_name = 'contributions/defaulters.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        today = timezone.localdate()
        month = int(self.request.GET.get('month', today.month))
        year = int(self.request.GET.get('year', today.year))

        paid_ids = Contribution.objects.filter(
            month=month, year=year
        ).values_list('member_id', flat=True)

        defaulters = Member.objects.exclude(id__in=paid_ids)
        ctx['defaulters'] = defaulters
        ctx['month'] = month
        ctx['year'] = year
        ctx['month_name'] = date(year, month, 1).strftime('%B')
        ctx['months'] = [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)]
        ctx['years'] = range(today.year - 2, today.year + 1)
        return ctx


class DefaultersExportView(MemberAccessMixin, View):
    """Export defaulters list as PDF."""
    def get(self, request):
        today = timezone.localdate()
        month = int(request.GET.get('month', today.month))
        year = int(request.GET.get('year', today.year))
        month_name = date(year, month, 1).strftime('%B')

        paid_ids = Contribution.objects.filter(
            month=month, year=year
        ).values_list('member_id', flat=True)

        defaulters = Member.objects.exclude(id__in=paid_ids).order_by('name')

        fields = [
            (lambda obj: obj.name, 'Member Name'),
            (lambda obj: obj.phone or '—', 'Phone'),
            (lambda obj: str(obj.date_joined), 'Date Joined'),
        ]

        title = f'Contribution Defaulters — {month_name} {year}'
        return export_pdf(defaulters, 'defaulters', title, fields)


class ContributionExportView(MemberAccessMixin, View):
    """Export contributions as CSV or PDF."""
    def get(self, request):
        return self._export(request)

    def post(self, request):
        return self._export(request)

    def _export(self, request):
        format_type = request.GET.get('format') or request.POST.get('format', 'csv')
        qs = Contribution.objects.select_related('member').all()
        
        # Check for explicitly selected IDs (from bulk selection)
        raw_ids = request.GET.get('ids') or request.POST.get('ids', '')
        if raw_ids:
            id_list = [int(i) for i in raw_ids.split(',') if i.strip().isdigit()]
            if id_list:
                qs = qs.filter(pk__in=id_list)
        else:
            # Apply same filters as list view
            q = request.GET.get('q', '').strip()
            month = request.GET.get('month', '').strip()
            year = request.GET.get('year', '').strip()
            payment_type = request.GET.get('payment_type', '').strip()
            if q:
                qs = qs.filter(member__name__icontains=q)
            if month:
                qs = qs.filter(month=month)
            if year:
                qs = qs.filter(year=year)
            if payment_type:
                qs = qs.filter(payment_type=payment_type)
        
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
        cash_total = qs.filter(payment_type='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        mpesa_total = qs.filter(payment_type='mpesa').aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        summary_cards = [
            ('Total Records', f'{total_count:,}'),
            ('Total Contributions', f'KES {total_amount:,.2f}'),
            ('Cash Collected', f'KES {cash_total:,.2f}'),
            ('M-Pesa Collected', f'KES {mpesa_total:,.2f}'),
        ]
        if not raw_ids:
            if month:
                from contributions.models import MONTH_CHOICES
                m_dict = dict(MONTH_CHOICES)
                m_label = m_dict.get(int(month), month) if str(month).isdigit() else month
                summary_cards.append(('Month', str(m_label)))
            if year:
                summary_cards.append(('Year', str(year)))
            if payment_type:
                summary_cards.append(('Method', dict(PAYMENT_TYPE_CHOICES).get(payment_type, payment_type.upper())))
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

        title = 'Selected Contributions Report' if raw_ids else 'Contributions Report'
        if format_type == 'pdf':
            return export_pdf(qs, 'contributions', title, fields, orientation='landscape', summary_cards=summary_cards, total_row=total_row)
        else:
            return export_csv(qs, 'contributions', fields, total_row=total_row)


class BulkContributionDeleteView(AdminRequiredMixin, View):
    """Bulk delete multiple contributions (requires admin password)."""
    
    def post(self, request):
        raw_ids = request.POST.get('contribution_ids', '')
        contribution_ids = [int(id) for id in raw_ids.split(',') if id.strip().isdigit()]
        
        if not contribution_ids:
            messages.error(request, "No contributions selected.")
            return redirect('contributions:list')
        
        contributions = Contribution.objects.filter(pk__in=contribution_ids).select_related('member')
        if not contributions.exists():
            messages.error(request, "Selected contributions no longer exist.")
            return redirect('contributions:list')
            
        total_amount = sum(c.amount for c in contributions)
        
        if request.POST.get('confirm') == 'true':
            password = request.POST.get('admin_password', '')
            reason = request.POST.get('delete_reason', '').strip()
            
            if not reason:
                return render(request, 'contributions/bulk_delete_confirm.html', {
                    'contributions': contributions,
                    'total_amount': total_amount,
                    'error': 'A reason for deletion is required.',
                    'contribution_ids': ','.join(str(id) for id in contribution_ids),
                    'delete_reason': reason,
                })
            
            if not request.user.check_password(password):
                return render(request, 'contributions/bulk_delete_confirm.html', {
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
                messages.success(request, f"{deleted_count} contribution(s) deleted successfully.")
            return redirect('contributions:list')
        
        return render(request, 'contributions/bulk_delete_confirm.html', {
            'contributions': contributions,
            'total_amount': total_amount,
            'contribution_ids': ','.join(str(id) for id in contribution_ids),
        })


class BulkContributionUpdateView(TreasurerRequiredMixin, View):
    """Bulk update fields (month, year, payment method) for selected contributions."""
    
    def post(self, request):
        raw_ids = request.POST.get('contribution_ids', '')
        contribution_ids = [int(id) for id in raw_ids.split(',') if id.strip().isdigit()]
        
        if not contribution_ids:
            messages.error(request, "No contributions selected.")
            return redirect('contributions:list')
            
        contributions = Contribution.objects.filter(pk__in=contribution_ids)
        if not contributions.exists():
            messages.error(request, "Selected contributions no longer exist.")
            return redirect('contributions:list')

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
            return redirect('contributions:list')
            
        with transaction.atomic():
            updated_count = 0
            for contrib in contributions:
                for field, val in updates.items():
                    setattr(contrib, field, val)
                contrib.save()
                updated_count += 1
                
        messages.success(request, f"{updated_count} contribution(s) updated successfully.")
        return redirect('contributions:list')


class BulkContributionView(TreasurerRequiredMixin, View):
    template_name = 'contributions/bulk_contribution.html'

    def _get_context(self, request, post_data=None):
        """Build context for both GET and failed POST renders."""
        import re
        from decimal import Decimal, InvalidOperation
        today = timezone.localdate()

        # Header defaults (from POST if re-rendering, else sensible defaults)
        default_date   = post_data.get('default_date', str(today)) if post_data else str(today)
        default_amount = post_data.get('default_amount', '') if post_data else ''
        default_method = post_data.get('default_method', 'cash') if post_data else 'cash'
        selected_month = int(post_data.get('month', today.month)) if post_data else today.month
        selected_year  = int(post_data.get('year', today.year))  if post_data else today.year

        # Members already paid this month/year
        already_paid_ids = set(
            Contribution.objects.filter(month=selected_month, year=selected_year)
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
                skip      = already_paid   # pre-skip members who already paid
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
            'rows':           rows,
            'default_date':   default_date,
            'default_amount': default_amount,
            'default_method': default_method,
            'selected_month': selected_month,
            'selected_year':  selected_year,
            'months':         months,
            'years':          years,
            'already_paid_count': len(already_paid_ids),
        }

    def get(self, request):
        return render(request, self.template_name, self._get_context(request))

    def post(self, request):
        import re
        from decimal import Decimal, InvalidOperation

        post = request.POST
        selected_month = int(post.get('month', timezone.localdate().month))
        selected_year  = int(post.get('year',  timezone.localdate().year))

        members = list(Member.objects.filter(is_active=True).order_by('name'))

        # ── Validate all rows first ───────────────────────────────
        to_save  = []   # list of dicts ready to create
        errors   = {}   # member_pk → error string
        skipped  = 0

        # Members who already have a contribution for the selected month/year
        already_paid_ids = set(
            Contribution.objects.filter(month=selected_month, year=selected_year)
            .values_list('member_id', flat=True)
        )

        for m in members:
            prefix = f'member_{m.pk}'
            # Always skip members who already paid — regardless of checkbox state
            skip = post.get(f'{prefix}_skip') == '1' or m.pk in already_paid_ids
            if skip:
                skipped += 1
                continue

            amount_str = post.get(f'{prefix}_amount', '').strip()
            pdate_str  = post.get(f'{prefix}_date', '').strip()
            ptype      = post.get(f'{prefix}_payment_type', 'cash')
            mcode      = post.get(f'{prefix}_mpesa_code', '').strip().upper()

            # Amount
            try:
                amount = Decimal(amount_str)
                if amount <= 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                errors[m.pk] = 'Enter a valid amount greater than zero.'
                continue

            # Date
            try:
                from datetime import datetime
                pdate = datetime.strptime(pdate_str, '%Y-%m-%d').date()
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
                'month':        selected_month,
                'year':         selected_year,
                'payment_type': ptype,
                'mpesa_code':   mcode,
            })

        # ── If any errors, re-render with error state ─────────────
        if errors:
            # Pack errors into post_data so _get_context can read them
            mutable = post.copy()
            for pk, msg in errors.items():
                mutable[f'_err_{pk}'] = msg
            ctx = self._get_context(request, mutable)
            ctx['selected_month'] = selected_month
            ctx['selected_year']  = selected_year
            messages.error(request, f'{len(errors)} row(s) have errors. Please fix them below.')
            return render(request, self.template_name, ctx)

        # ── Save all valid rows in one transaction ────────────────
        if not to_save:
            messages.warning(request, 'No contributions to record — all rows were skipped.')
            return redirect('contributions:bulk')

        with transaction.atomic():
            created = []
            for row in to_save:
                c = Contribution.objects.create(
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
            f'{len(created)} contribution(s) recorded successfully.'
            + (f' {skipped} skipped.' if skipped else '')
        )
        return redirect('contributions:list')
