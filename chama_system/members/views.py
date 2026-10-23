from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.views import View
from django.urls import reverse_lazy
from django.db import models
from django.db.models import Sum, Count
from django.contrib import messages
from django.shortcuts import redirect, render
import csv
import io
from .models import Member, RegistrationFeeRate
from .forms import MemberForm, RegistrationFeeRateForm
from accounts.mixins import TreasurerRequiredMixin, AdminRequiredMixin, MemberAccessMixin, AdminPasswordDeleteMixin
from utils.exports import export_csv, export_pdf
from django.utils import timezone


SORT_OPTIONS = {
    'name_asc':          ('name',                    'A → Z'),
    'name_desc':         ('-name',                   'Z → A'),
    'newest':            ('-date_joined',             'Newest First'),
    'oldest':            ('date_joined',              'Oldest First'),
    'contributions_desc':('-total_contributions_sum', 'Most Contributions'),
    'contributions_asc': ('total_contributions_sum',  'Least Contributions'),
}


class MemberListView(MemberAccessMixin, ListView):
    model = Member
    template_name = 'members/member_list.html'
    context_object_name = 'members'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('exit_record').annotate(
            total_contributions_sum=Sum('contribution__amount')
        )
        q = self.request.GET.get('q', '').strip()
        if q:
            # Build phone variants to handle mixed storage formats:
            # user types 0717147007  → also search +254717147007 / 254717147007
            # user types +254717... → also search 0717... / 254717...
            phone_variants = [q]
            digits = q.lstrip('+')
            if digits.startswith('0') and len(digits) >= 9:
                # local format → add international variants
                core = digits[1:]  # strip leading 0
                phone_variants += ['+254' + core, '254' + core]
            elif digits.startswith('254') and len(digits) >= 12:
                core = digits[3:]  # strip 254
                phone_variants += ['0' + core, '+254' + core]
            elif digits.startswith('7') or digits.startswith('1'):
                # bare number without prefix
                phone_variants += ['0' + digits, '+254' + digits, '254' + digits]

            phone_q = models.Q()
            for variant in phone_variants:
                phone_q |= models.Q(phone__icontains=variant)

            qs = qs.filter(models.Q(name__icontains=q) | phone_q)

        sort = self.request.GET.get('sort', 'name_asc')
        order = SORT_OPTIONS.get(sort, SORT_OPTIONS['name_asc'])[0]
        qs = qs.order_by(order)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_sort'] = self.request.GET.get('sort', 'name_asc')
        ctx['sort_options'] = [(k, v[1]) for k, v in SORT_OPTIONS.items()]
        return ctx


class MemberCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    model = Member
    form_class = MemberForm
    template_name = 'members/member_form.html'
    success_url = reverse_lazy('members:list')
    success_message = "Member added successfully."

    def form_valid(self, form):
        """
        Handle registration fee toggle:
        - If checked: apply current registration fee rate and create payment record
        - If unchecked: set to 0 (admin can add payment later)
        """
        from .models import RegistrationFeeRate, RegistrationFeePayment
        from decimal import Decimal
        
        fee_paid = form.cleaned_data.get('registration_fee_paid_toggle', False)
        amt = Decimal('0')
        if fee_paid:
            current_rate = RegistrationFeeRate.current_rate()
            amt = current_rate.amount if current_rate else Decimal('0')
        
        form.instance.registration_fee_paid = amt
        response = super().form_valid(form)

        if fee_paid and amt > 0:
            RegistrationFeePayment.objects.create(
                member=self.object,
                amount=amt,
                payment_date=self.object.date_joined,
                payment_method='cash',
                notes='Paid on member registration',
                recorded_by=self.request.user if self.request.user.is_authenticated else None,
            )

        return response


class MemberUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Member
    form_class = MemberForm
    template_name = 'members/member_form.html'
    success_url = reverse_lazy('members:list')
    success_message = "Member updated successfully."

    def form_valid(self, form):
        """
        Handle registration fee toggle on edit:
        - If checked: apply current registration fee rate (if not already paid) and record payment
        - If unchecked: clear fee payments and set to 0
        """
        from .models import RegistrationFeeRate, RegistrationFeePayment
        from decimal import Decimal
        
        fee_paid = form.cleaned_data.get('registration_fee_paid_toggle', False)
        
        if fee_paid:
            if form.instance.registration_fee_paid == 0:
                current_rate = RegistrationFeeRate.current_rate()
                amt = current_rate.amount if current_rate else Decimal('0')
                form.instance.registration_fee_paid = amt
                response = super().form_valid(form)
                if amt > 0:
                    RegistrationFeePayment.objects.create(
                        member=self.object,
                        amount=amt,
                        payment_date=self.object.date_joined,
                        payment_method='cash',
                        notes='Paid on member profile update',
                        recorded_by=self.request.user if self.request.user.is_authenticated else None,
                    )
                return response
        else:
            form.instance.registration_fee_paid = Decimal('0')
            form.instance.fee_payments.all().delete()
        
        return super().form_valid(form)


class MemberDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, SuccessMessageMixin, DeleteView):
    model = Member
    template_name = 'members/member_confirm_delete.html'
    success_url = reverse_lazy('members:list')
    success_message = "Member deleted."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        member = self.object
        contrib_count = member.contribution_set.count()
        loan_count = member.loan_set.count()
        payment_count = member.payment_set.count()
        penalty_count = member.penalties.count()
        welfare_count = member.welfare_contributions.count()
        ctx['contrib_count'] = contrib_count
        ctx['loan_count'] = loan_count
        ctx['payment_count'] = payment_count
        ctx['penalty_count'] = penalty_count
        ctx['welfare_count'] = welfare_count
        ctx['has_financial_history'] = any([contrib_count, loan_count, payment_count, penalty_count, welfare_count])
        return ctx

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except models.ProtectedError:
            messages.error(
                self.request,
                f"Cannot delete member '{self.object.name}' because they have protected records (such as an existing exit settlement or year-end payout)."
            )
            return redirect('members:detail', pk=self.object.pk)


class MemberDetailView(MemberAccessMixin, DetailView):
    model = Member
    template_name = 'members/member_detail.html'
    context_object_name = 'member'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from django.db.models import Sum
        from loans.models import LoanGuarantor
        from welfare.models import WelfareContribution

        ctx['contributions'] = self.object.contribution_set.order_by('-date')
        ctx['loans'] = self.object.loan_set.all()
        ctx['payments'] = self.object.payment_set.select_related('loan').order_by('-date')

        penalties = self.object.penalties.all()
        ctx['penalties'] = penalties
        ctx['total_penalties_issued'] = penalties.aggregate(t=Sum('amount'))['t'] or 0
        ctx['total_penalties_paid'] = penalties.filter(paid=True).aggregate(t=Sum('amount'))['t'] or 0
        ctx['total_penalties_outstanding'] = penalties.filter(paid=False).aggregate(t=Sum('amount'))['t'] or 0

        ctx['guarantees'] = LoanGuarantor.objects.filter(
            guarantor=self.object
        ).select_related('loan__member')

        # Welfare contributions
        ctx['welfare_contributions'] = WelfareContribution.objects.filter(
            member=self.object
        ).order_by('-date')
        ctx['total_welfare_contributions'] = (
            WelfareContribution.objects.filter(member=self.object)
            .aggregate(t=Sum('amount'))['t'] or 0
        )

        # Year-end expected payout (live estimate)
        # Optimised: compute only for this one member rather than loading all 1000
        try:
            from contributions.models import Contribution as _Contrib
            from django.db.models import Sum as _Sum, F as _F, ExpressionWrapper as _EW, DecimalField as _DC
            from loans.models import Loan as _Loan
            from penalties.models import Penalty as _Pen
            from decimal import Decimal as _D, ROUND_DOWN

            # Total income — reg fees excluded (separate fund)
            total_contrib_income = _Contrib.objects.aggregate(t=_Sum('amount'))['t'] or _D('0')
            total_pen_income     = _Pen.objects.filter(paid=True).aggregate(t=_Sum('amount'))['t'] or _D('0')
            loans_qs = _Loan.objects.annotate(
                interest_charged=_EW(_F('total_payable') - _F('loan_amount'), output_field=_DC())
            ).only('amount_paid', 'total_payable', 'loan_amount')
            interest_collected = sum(min(l.amount_paid, l.interest_charged) for l in loans_qs)
            total_income = total_contrib_income + _D(str(interest_collected)) + total_pen_income

            # This member's contribution
            my_contrib = _D(str(self.object.total_contributions() or 0))
            reg_fee    = self.object.registration_fee_paid or _D('0')  # info only

            # Total contributions of ALL active members
            total_all_contrib = _Contrib.objects.filter(
                member__is_active=True
            ).aggregate(t=_Sum('amount'))['t'] or _D('0')

            # Principal back = contributions only (no reg fees in year-end)
            total_principal_back = total_all_contrib
            profit_pool = max(total_income - total_principal_back, _D('0'))

            my_profit = (
                (my_contrib / total_all_contrib * profit_pool).quantize(_D('0.01'), rounding=ROUND_DOWN)
                if total_all_contrib > 0 and profit_pool > 0 else _D('0')
            )
            gross_return = my_contrib + my_profit
            outstanding_loans = _D(str(self.object.total_loan_balance() or 0))
            outstanding_penalties = _D(str(self.object.total_penalties_unpaid() or 0))
            total_deductions = outstanding_loans + outstanding_penalties
            net_return = max(gross_return - total_deductions, _D('0.00'))
            deficit = max(total_deductions - gross_return, _D('0.00'))

            ctx['yearend_preview'] = {
                'contributions':         my_contrib,
                'reg_fee':               reg_fee,       # shown for info only
                'principal_back':        my_contrib,    # contributions only
                'interest_share':        my_profit,
                'gross_return':          gross_return,
                'outstanding_loans':     outstanding_loans,
                'outstanding_penalties': outstanding_penalties,
                'total_deductions':      total_deductions,
                'total':                 net_return,
                'deficit':               deficit,
            }
        except Exception:
            ctx['yearend_preview'] = None

        # Registration fee payments history
        ctx['fee_payments'] = self.object.fee_payments.all().order_by('-payment_date')

        # Aggregated stats
        total_contrib = self.object.total_contributions() or 0
        total_welfare = ctx['total_welfare_contributions'] or 0
        reg_fee_paid = self.object.registration_fee_paid or 0
        total_loans_val = self.object.total_loans() or 0
        total_loan_bal = self.object.total_loan_balance() or 0
        penalties_out = ctx['total_penalties_outstanding'] or 0

        ctx['total_contributions'] = total_contrib
        ctx['total_loans'] = total_loans_val
        ctx['total_loan_balance'] = total_loan_bal
        ctx['total_loan_paid'] = sum((l.amount_paid or 0) for l in ctx['loans'])
        ctx['active_loans_count'] = ctx['loans'].exclude(status='cleared').count()
        ctx['cleared_loans_count'] = ctx['loans'].filter(status='cleared').count()
        ctx['total_guaranteed_amount'] = sum((g.amount_guaranteed or 0) for g in ctx['guarantees'])
        ctx['guarantee_liability'] = sum((g.loan.balance or 0) for g in ctx['guarantees'] if g.loan and g.loan.balance > 0)
        ctx['net_equity'] = total_contrib + total_welfare + reg_fee_paid - total_loan_bal - penalties_out

        # Unified recent activity stream
        activities = []
        for c in ctx['contributions'][:6]:
            activities.append({
                'type': 'contribution',
                'title': f"Monthly Contribution ({c.get_month_display()} {c.year})",
                'amount': c.amount,
                'date': c.date,
                'is_inflow': True,
                'badge': 'Savings',
                'badge_class': 'bg-primary-subtle text-primary',
                'icon': 'bi-piggy-bank',
                'color': '#2563eb',
            })
        for w in ctx['welfare_contributions'][:6]:
            activities.append({
                'type': 'welfare',
                'title': f"Welfare Contribution ({w.get_month_display()} {w.year})",
                'amount': w.amount,
                'date': w.date,
                'is_inflow': True,
                'badge': 'Welfare',
                'badge_class': 'bg-danger-subtle text-danger',
                'icon': 'bi-heart-pulse',
                'color': '#e11d48',
            })
        for p in ctx['payments'][:6]:
            activities.append({
                'type': 'payment',
                'title': f"Loan Repayment ({p.get_payment_type_display() if hasattr(p, 'get_payment_type_display') else p.payment_type})",
                'amount': p.amount,
                'date': p.date,
                'is_inflow': True,
                'badge': 'Repayment',
                'badge_class': 'bg-success-subtle text-success',
                'icon': 'bi-cash-coin',
                'color': '#16a34a',
            })
        for l in ctx['loans'][:6]:
            activities.append({
                'type': 'loan',
                'title': f"Loan Issued (Payable: KES {l.total_payable:,.2f})",
                'amount': l.loan_amount,
                'date': l.date_taken,
                'is_inflow': False,
                'badge': f"Loan - {l.get_status_display()}",
                'badge_class': 'bg-warning-subtle text-warning',
                'icon': 'bi-credit-card',
                'color': '#d97706',
            })
        for pen in ctx['penalties'][:6]:
            activities.append({
                'type': 'penalty',
                'title': f"Penalty: {pen.reason}",
                'amount': pen.amount,
                'date': pen.date,
                'is_inflow': False,
                'badge': 'Paid' if pen.paid else 'Unpaid Penalty',
                'badge_class': 'bg-success-subtle text-success' if pen.paid else 'bg-danger-subtle text-danger',
                'icon': 'bi-exclamation-triangle',
                'color': '#e11d48',
            })
        for fp in ctx['fee_payments'][:4]:
            activities.append({
                'type': 'reg_fee',
                'title': f"Registration Fee ({fp.get_payment_method_display()})",
                'amount': fp.amount,
                'date': fp.payment_date,
                'is_inflow': True,
                'badge': 'Reg. Fee',
                'badge_class': 'bg-info-subtle text-info',
                'icon': 'bi-ticket-perforated',
                'color': '#0891b2',
            })

        activities.sort(key=lambda x: str(x['date']), reverse=True)
        ctx['recent_activity'] = activities[:8]

        return ctx


class MemberImportView(TreasurerRequiredMixin, TemplateView):
    template_name = 'members/member_import.html'

    def post(self, request, *args, **kwargs):
        csv_file = request.FILES.get('csv_file')
        if not csv_file or not csv_file.name.endswith('.csv'):
            messages.error(request, "Please upload a valid .csv file.")
            return redirect('members:import')

        # Decode with BOM-safe utf-8-sig so Excel-exported CSVs work correctly
        try:
            decoded = csv_file.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded = csv_file.read().decode('latin-1')

        reader = csv.DictReader(io.StringIO(decoded))

        # Normalise header names: strip whitespace and lowercase
        # This handles "Name", "NAME", " name ", etc.
        raw_headers = reader.fieldnames or []
        norm_map = {h.strip().lower(): h for h in raw_headers}
        reader.fieldnames = [h.strip().lower() for h in raw_headers]

        created, skipped, errors = 0, 0, []

        for i, row in enumerate(reader, start=1):
            # Strip whitespace from all values
            row = {k: (v.strip() if v else '') for k, v in row.items()}

            name     = row.get('name', '').strip()
            phone    = row.get('phone', '').strip()
            date_joined = row.get('date_joined', '').strip()

            if not name:
                errors.append(f"Row {i}: 'name' column is missing or empty.")
                continue

            if not phone:
                errors.append(f"Row {i} ({name}): 'phone' column is missing or empty.")
                continue

            if Member.objects.filter(phone=phone).exists():
                skipped += 1
                continue

            try:
                kwargs = dict(name=name, phone=phone)
                if date_joined:
                    from datetime import datetime
                    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y'):
                        try:
                            kwargs['date_joined'] = datetime.strptime(date_joined, fmt).date()
                            break
                        except ValueError:
                            pass
                Member.objects.create(**kwargs)
                created += 1
            except Exception as e:
                errors.append(f"Row {i} ({name}): {e}")

        if created:
            messages.success(request, f"{created} member(s) imported successfully.")
        if skipped:
            messages.warning(request, f"{skipped} row(s) skipped (duplicate phone number).")
        for err in errors:
            messages.error(request, err)

        return redirect('members:list')


class MemberExportView(MemberAccessMixin, View):
    def get(self, request):
        from contributions.models import Contribution
        from welfare.models import WelfareContribution
        from django.db.models import OuterRef, Subquery, Sum, DecimalField
        from django.db.models.functions import Coalesce
        from decimal import Decimal

        format_type = request.GET.get('format', 'csv')

        contrib_sub = Contribution.objects.filter(member=OuterRef('pk')).values('member').annotate(total=Sum('amount')).values('total')
        welfare_sub = WelfareContribution.objects.filter(member=OuterRef('pk')).values('member').annotate(total=Sum('amount')).values('total')

        qs = Member.objects.annotate(
            total_contributions_sum=Coalesce(Subquery(contrib_sub, output_field=DecimalField()), Decimal('0.00')),
            total_welfare_sum=Coalesce(Subquery(welfare_sub, output_field=DecimalField()), Decimal('0.00')),
        )
        q = request.GET.get('q', '').strip()
        if q:
            digits = q.lstrip('+')
            phone_variants = [q]
            if digits.startswith('0') and len(digits) >= 9:
                core = digits[1:]
                phone_variants += ['+254' + core, '254' + core]
            elif digits.startswith('254') and len(digits) >= 12:
                core = digits[3:]
                phone_variants += ['0' + core, '+254' + core]
            elif digits.startswith('7') or digits.startswith('1'):
                phone_variants += ['0' + digits, '+254' + digits, '254' + digits]
            phone_q = models.Q()
            for variant in phone_variants:
                phone_q |= models.Q(phone__icontains=variant)
            qs = qs.filter(models.Q(name__icontains=q) | phone_q)
        sort = request.GET.get('sort', 'name_asc')
        order = SORT_OPTIONS.get(sort, SORT_OPTIONS['name_asc'])[0]
        qs = qs.order_by(order)

        total_reg = sum((m.registration_fee_paid or Decimal('0')) for m in qs)
        total_contrib = sum((m.total_contributions_sum or Decimal('0')) for m in qs)
        total_welfare = sum((m.total_welfare_sum or Decimal('0')) for m in qs)
        combined_total = total_contrib + total_welfare

        summary_cards = [
            ('Total Members', f'{qs.count():,}'),
            ('Total Reg. Fees', f'KES {total_reg:,.2f}'),
            ('Total Regular Contributions', f'KES {total_contrib:,.2f}'),
            ('Total Welfare Contributions', f'KES {total_welfare:,.2f}'),
            ('Combined Total', f'KES {combined_total:,.2f}'),
        ]

        total_row = [
            'TOTAL SUMMARY',
            '',
            '',
            f'KES {total_reg:,.2f}',
            f'KES {total_contrib:,.2f}',
            f'KES {total_welfare:,.2f}',
            f'KES {combined_total:,.2f}',
        ]

        fields = [
            ('name', 'Name'),
            ('phone', 'Phone'),
            ('date_joined', 'Date Joined'),
            ('registration_fee_paid', 'Reg. Fee (KES)'),
            (lambda obj: f"KES {obj.total_contributions_sum or Decimal('0'):,.2f}", 'Total Contributions'),
            (lambda obj: f"KES {obj.total_welfare_sum or Decimal('0'):,.2f}", 'Total Welfare Contributions'),
            (lambda obj: f"KES {(obj.total_contributions_sum or Decimal('0')) + (obj.total_welfare_sum or Decimal('0')):,.2f}", 'Combined Total'),
        ]
        if format_type == 'pdf':
            return export_pdf(qs, 'members', 'Members List', fields, orientation='landscape', summary_cards=summary_cards, total_row=total_row)
        return export_csv(qs, 'members', fields, total_row=total_row)


class BulkMemberExitView(TreasurerRequiredMixin, View):
    """Bulk exit multiple members."""
    
    def post(self, request):
        member_ids = request.POST.get('member_ids', '').split(',')
        member_ids = [int(id) for id in member_ids if id.strip()]
        
        if not member_ids:
            messages.error(request, "No members selected.")
            return redirect('members:list')
        
        from .exit_views import _compute_exit_summary
        from django.db import transaction
        from .models import MemberExit
        from decimal import Decimal
        from django.utils import timezone
        
        members = Member.objects.filter(pk__in=member_ids, is_active=True)
        exited_count = 0
        blocked_count = 0
        blocked_members = []
        
        with transaction.atomic():
            for member in members:
                # Check if already exited
                if hasattr(member, 'exit_record'):
                    blocked_count += 1
                    blocked_members.append(f"{member.name} (already exited)")
                    continue
                
                summary = _compute_exit_summary(member)
                
                # Check if blocked (has pending loans or penalties)
                if summary['is_blocked']:
                    blocked_count += 1
                    blocked_members.append(f"{member.name} ({', '.join(summary['blockers'][:1])})")
                    continue
                
                # Exit the member
                try:
                    MemberExit.objects.create(
                        member=member,
                        exit_date=timezone.localdate(),
                        contributions_returned=summary['contributions'],
                        reg_fee_returned=Decimal('0.00'),
                        profit_share_paid=summary['profit_share'],
                        outstanding_loans_deducted=Decimal('0.00'),
                        outstanding_penalties_deducted=Decimal('0.00'),
                        net_payout=summary['net_payout'],
                        notes='Bulk exit',
                        recorded_by=request.user,
                    )
                    Member.objects.filter(pk=member.pk).update(is_active=False)
                    exited_count += 1
                except Exception as e:
                    blocked_count += 1
                    blocked_members.append(f"{member.name} (Error: {str(e)[:30]})")
        
        if exited_count:
            messages.success(request, f"{exited_count} member(s) exited successfully.")
        
        if blocked_count:
            if len(blocked_members) <= 5:
                for member_info in blocked_members:
                    messages.warning(request, f"Could not exit: {member_info}")
            else:
                messages.warning(request, f"{blocked_count} member(s) could not be exited (check loans/penalties or already exited).")
        
        return redirect('members:list')


class BulkMemberDeleteView(AdminRequiredMixin, View):
    """Bulk delete multiple members (requires admin password)."""
    
    def post(self, request):
        member_ids = request.POST.get('member_ids', '').split(',')
        member_ids = [int(id) for id in member_ids if id.strip()]
        
        if not member_ids:
            messages.error(request, "No members selected.")
            return redirect('members:list')
        
        # Redirect to confirmation page with selected IDs
        from django.shortcuts import render
        members = Member.objects.filter(pk__in=member_ids)
        
        if request.POST.get('confirm') == 'true':
            # Process actual deletion with password confirmation
            password = request.POST.get('admin_password', '')
            reason = request.POST.get('delete_reason', '').strip()
            
            if not reason:
                return render(request, 'members/member_bulk_delete_confirm.html', {
                    'members': members,
                    'error': 'Deletion reason is required.',
                    'member_ids': ','.join(str(id) for id in member_ids),
                })
            
            if not request.user.check_password(password):
                return render(request, 'members/member_bulk_delete_confirm.html', {
                    'members': members,
                    'error': 'Incorrect password. Deletion cancelled.',
                    'member_ids': ','.join(str(id) for id in member_ids),
                })
            
            # Delete members
            from recycle_bin.models import DeletedRecord
            from recycle_bin.serializer import serialize_instance
            from django.db import transaction
            
            deleted_count = 0
            failed_members = []
            for member in members:
                try:
                    with transaction.atomic():
                        # Save to recycle bin
                        data = serialize_instance(member)
                        DeletedRecord.objects.create(
                            app_label=member._meta.app_label,
                            model_name=member._meta.model_name,
                            object_id=str(member.pk),
                            object_repr=str(member)[:300],
                            data=data,
                            delete_reason=reason,
                            deleted_by=request.user,
                        )
                        # Delete member
                        member.delete()
                        deleted_count += 1
                except Exception as e:
                    failed_members.append(f"{member.name}: {str(e)[:60]}")
            
            if deleted_count:
                messages.success(request, f"{deleted_count} member(s) deleted successfully.")
            if failed_members:
                for err in failed_members[:5]:
                    messages.error(request, f"Could not delete {err}")
                if len(failed_members) > 5:
                    messages.error(request, f"...and {len(failed_members) - 5} more member(s) could not be deleted.")
            
            return redirect('members:list')
        
        # Show confirmation page
        return render(request, 'members/member_bulk_delete_confirm.html', {
            'members': members,
            'member_ids': ','.join(str(id) for id in member_ids),
        })


class RegistrationFeePaymentListView(MemberAccessMixin, ListView):
    """List all registration fee payments with filtering and sorting."""
    model = Member
    template_name = 'members/fee_payment_list.html'
    context_object_name = 'payments'
    paginate_by = 50

    def get_queryset(self):
        from .models import RegistrationFeePayment
        qs = RegistrationFeePayment.objects.select_related('member', 'recorded_by').order_by('-payment_date')
        
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(models.Q(member__name__icontains=q) | models.Q(receipt_number__icontains=q))
        
        payment_method = self.request.GET.get('payment_method', '').strip()
        if payment_method:
            qs = qs.filter(payment_method=payment_method)
        
        return qs

    def get_context_data(self, **kwargs):
        from .models import RegistrationFeePayment
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['payment_method'] = self.request.GET.get('payment_method', '')
        ctx['payment_methods'] = RegistrationFeePayment._meta.get_field('payment_method').choices
        
        # Add summary stats
        from django.db.models import Sum
        all_payments = RegistrationFeePayment.objects.all()
        ctx['total_payments'] = all_payments.aggregate(t=Sum('amount'))['t'] or 0
        ctx['payment_count'] = all_payments.count()
        
        return ctx


class RegistrationFeePaymentAddView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    """Record a registration fee payment."""
    model = Member
    form_class = None
    template_name = 'members/fee_payment_form.html'
    success_url = reverse_lazy('members:fee_payment_list')
    success_message = "Registration fee payment recorded successfully."

    def get(self, request, *args, **kwargs):
        from .forms import RegistrationFeePaymentForm
        context = self.get_context_data()
        context['form'] = RegistrationFeePaymentForm()
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs):
        from .models import RegistrationFeePayment
        from .forms import RegistrationFeePaymentForm
        
        form = RegistrationFeePaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.recorded_by = request.user
            payment.save()
            messages.success(request, self.success_message)
            return redirect(self.success_url)
        
        context = self.get_context_data()
        context['form'] = form
        return self.render_to_response(context)


class RegistrationFeePaymentBulkView(TreasurerRequiredMixin, View):
    """Bulk entry of registration fee payments for multiple members."""
    template_name = 'members/fee_payment_bulk.html'

    def _get_context(self, request, post_data=None):
        from decimal import Decimal
        from .models import RegistrationFeeRate, RegistrationFeePayment
        today = timezone.localdate()
        current_rate = RegistrationFeeRate.current_rate()
        rate_amount = current_rate.amount if current_rate else Decimal('0.00')

        default_date = post_data.get('default_date', str(today)) if post_data else str(today)
        default_amount = post_data.get('default_amount', str(rate_amount) if rate_amount > 0 else '') if post_data else (str(rate_amount) if rate_amount > 0 else '')
        default_method = post_data.get('default_method', 'cash') if post_data else 'cash'

        members = list(Member.objects.filter(is_active=True).order_by('name'))
        
        rows = []
        paid_members_count = 0
        unpaid_members_count = 0

        for m in members:
            prefix = f'member_{m.pk}'
            total_paid = m.registration_fee_paid or Decimal('0.00')
            is_fully_paid = (total_paid >= rate_amount and rate_amount > 0) or (rate_amount == 0 and total_paid > 0)
            
            if is_fully_paid:
                paid_members_count += 1
                remaining_due = Decimal('0.00')
            else:
                unpaid_members_count += 1
                if rate_amount > 0:
                    remaining_due = max(Decimal('0.00'), rate_amount - total_paid)
                else:
                    remaining_due = Decimal('0.00')

            if post_data:
                skip = post_data.get(f'{prefix}_skip') == '1'
                amount = post_data.get(f'{prefix}_amount', '').strip()
                pdate = post_data.get(f'{prefix}_date', '').strip()
                ptype = post_data.get(f'{prefix}_payment_type', 'cash')
                receipt = post_data.get(f'{prefix}_receipt_number', '').strip()
                notes = post_data.get(f'{prefix}_notes', '').strip()
                row_error = post_data.get(f'_err_{m.pk}', '')
            else:
                skip = is_fully_paid
                amount = str(remaining_due) if remaining_due > 0 else (default_amount or '0.00')
                pdate = default_date
                ptype = default_method
                receipt = ''
                notes = ''
                row_error = ''

            rows.append({
                'member': m,
                'prefix': prefix,
                'total_paid': total_paid,
                'is_fully_paid': is_fully_paid,
                'remaining_due': remaining_due,
                'skip': skip,
                'amount': amount,
                'date': pdate,
                'payment_type': ptype,
                'receipt_number': receipt,
                'notes': notes,
                'error': row_error,
            })

        all_payments = RegistrationFeePayment.objects.all()
        total_fund_collected = all_payments.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

        return {
            'rows': rows,
            'current_rate': current_rate,
            'rate_amount': rate_amount,
            'default_date': default_date,
            'default_amount': default_amount,
            'default_method': default_method,
            'total_members_count': len(members),
            'paid_members_count': paid_members_count,
            'unpaid_members_count': unpaid_members_count,
            'total_fund_collected': total_fund_collected,
            'payment_methods': RegistrationFeePayment._meta.get_field('payment_method').choices,
        }

    def get(self, request):
        return render(request, self.template_name, self._get_context(request))

    def post(self, request):
        from decimal import Decimal, InvalidOperation
        from datetime import datetime
        from django.db import transaction
        from .models import RegistrationFeePayment

        post = request.POST
        members = list(Member.objects.filter(is_active=True).order_by('name'))

        to_save = []
        errors = {}
        skipped = 0

        valid_methods = [val for val, label in RegistrationFeePayment._meta.get_field('payment_method').choices]

        for m in members:
            prefix = f'member_{m.pk}'
            skip = post.get(f'{prefix}_skip') == '1'
            if skip:
                skipped += 1
                continue

            amount_str = post.get(f'{prefix}_amount', '').strip()
            pdate_str = post.get(f'{prefix}_date', '').strip()
            ptype = post.get(f'{prefix}_payment_type', 'cash').strip()
            receipt = post.get(f'{prefix}_receipt_number', '').strip()
            notes = post.get(f'{prefix}_notes', '').strip()

            # Validate amount
            try:
                amount = Decimal(amount_str)
                if amount <= 0:
                    raise ValueError
            except (InvalidOperation, ValueError):
                errors[m.pk] = 'Enter a valid amount greater than zero.'
                continue

            # Validate date
            try:
                pdate = datetime.strptime(pdate_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                errors[m.pk] = 'Enter a valid date (YYYY-MM-DD).'
                continue

            # Validate payment method
            if ptype not in valid_methods:
                errors[m.pk] = f'Invalid payment method.'
                continue

            to_save.append({
                'member': m,
                'amount': amount,
                'payment_date': pdate,
                'payment_method': ptype,
                'receipt_number': receipt,
                'notes': notes,
                'recorded_by': request.user,
            })

        if errors:
            mutable = post.copy()
            for pk, msg in errors.items():
                mutable[f'_err_{pk}'] = msg
            ctx = self._get_context(request, mutable)
            messages.error(request, "Please correct the highlighted errors below before saving.")
            return render(request, self.template_name, ctx)

        if not to_save:
            messages.warning(request, "No member payments were selected to record.")
            return redirect('members:fee_payment_bulk')

        created_count = 0
        total_amount = Decimal('0.00')
        with transaction.atomic():
            for item in to_save:
                RegistrationFeePayment.objects.create(
                    member=item['member'],
                    amount=item['amount'],
                    payment_date=item['payment_date'],
                    payment_method=item['payment_method'],
                    receipt_number=item['receipt_number'],
                    notes=item['notes'],
                    recorded_by=item['recorded_by'],
                )
                created_count += 1
                total_amount += item['amount']

        messages.success(
            request,
            f"Successfully recorded registration fee payments for {created_count} member(s) totaling KES {total_amount:,.2f}."
        )
        return redirect('members:fee_payment_list')


class RegistrationFeePaymentImportView(TreasurerRequiredMixin, TemplateView):
    """Import registration fee payment dates from CSV."""
    template_name = 'members/fee_payment_import.html'

    def post(self, request, *args, **kwargs):
        from .models import RegistrationFeePayment
        from decimal import Decimal
        from datetime import datetime

        csv_file = request.FILES.get('csv_file')
        if not csv_file or not csv_file.name.endswith('.csv'):
            messages.error(request, "Please upload a valid .csv file.")
            return redirect('members:fee_payment_import')

        # Decode CSV
        try:
            decoded = csv_file.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            decoded = csv_file.read().decode('latin-1')

        reader = csv.DictReader(io.StringIO(decoded))

        # Normalize headers
        raw_headers = reader.fieldnames or []
        reader.fieldnames = [h.strip().lower() for h in raw_headers]

        created, skipped, errors = 0, 0, []

        for i, row in enumerate(reader, start=1):
            row = {k: (v.strip() if v else '') for k, v in row.items()}

            phone = row.get('phone', '').strip()
            amount = row.get('amount', '0').strip() or '0'
            payment_date = row.get('payment_date', '').strip()
            payment_method = row.get('payment_method', 'cash').strip().lower()
            receipt_number = row.get('receipt_number', '').strip()

            if not phone:
                errors.append(f"Row {i}: 'phone' is required.")
                continue

            # Find member
            try:
                member = Member.objects.get(phone=phone)
            except Member.DoesNotExist:
                errors.append(f"Row {i}: Member with phone {phone} not found.")
                continue
            except Member.MultipleObjectsReturned:
                errors.append(f"Row {i}: Multiple members with phone {phone}.")
                continue

            # Parse date
            if not payment_date:
                errors.append(f"Row {i} ({member.name}): 'payment_date' is required.")
                continue

            parsed_date = None
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y', '%d.%m.%Y'):
                try:
                    parsed_date = datetime.strptime(payment_date, fmt).date()
                    break
                except ValueError:
                    pass

            if not parsed_date:
                errors.append(f"Row {i} ({member.name}): Invalid date format '{payment_date}'. Use YYYY-MM-DD or DD/MM/YYYY.")
                continue

            # Validate payment method
            valid_methods = ['cash', 'mpesa', 'bank_transfer', 'cheque']
            if payment_method not in valid_methods:
                errors.append(f"Row {i} ({member.name}): Invalid payment method '{payment_method}'. Use: {', '.join(valid_methods)}")
                continue

            # Check if already exists
            if RegistrationFeePayment.objects.filter(member=member, payment_date=parsed_date).exists():
                skipped += 1
                continue

            # Create payment record
            try:
                RegistrationFeePayment.objects.create(
                    member=member,
                    amount=Decimal(amount),
                    payment_date=parsed_date,
                    payment_method=payment_method,
                    receipt_number=receipt_number,
                    recorded_by=request.user,
                )
                created += 1
            except Exception as e:
                errors.append(f"Row {i} ({member.name}): {str(e)[:60]}")

        if created:
            messages.success(request, f"{created} registration fee payment(s) imported successfully.")
        if skipped:
            messages.warning(request, f"{skipped} payment(s) skipped (duplicate date or already exists).")
        for err in errors:
            messages.error(request, err)

        return redirect('members:fee_payment_list')


class RegistrationFeeRateListView(MemberAccessMixin, ListView):
    """List all registration fee rates."""
    model = RegistrationFeeRate
    template_name = 'members/fee_rate_list.html'
    context_object_name = 'rates'
    paginate_by = 20

    def get_queryset(self):
        return RegistrationFeeRate.objects.all()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['current_rate'] = RegistrationFeeRate.current_rate()
        return ctx


class RegistrationFeeRateCreateView(TreasurerRequiredMixin, SuccessMessageMixin, CreateView):
    """Create a new registration fee rate."""
    model = RegistrationFeeRate
    form_class = RegistrationFeeRateForm
    template_name = 'members/fee_rate_form.html'
    success_url = reverse_lazy('members:fee_rate_list')
    success_message = "Registration fee rate created successfully."

    def get_initial(self):
        initial = super().get_initial()
        initial['effective_date'] = timezone.localdate()
        return initial


class RegistrationFeeRateUpdateView(TreasurerRequiredMixin, SuccessMessageMixin, UpdateView):
    """Update a registration fee rate."""
    model = RegistrationFeeRate
    form_class = RegistrationFeeRateForm
    template_name = 'members/fee_rate_form.html'
    success_url = reverse_lazy('members:fee_rate_list')
    success_message = "Registration fee rate updated successfully."
