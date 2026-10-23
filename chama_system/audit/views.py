from django.views.generic import ListView
from django.views import View
from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from accounts.mixins import AdminRequiredMixin
from .models import AuditLog


class AuditLogListView(AdminRequiredMixin, ListView):
    model = AuditLog
    template_name = 'audit/audit_log.html'
    context_object_name = 'logs'
    paginate_by = 50

    def get_queryset(self):
        qs = AuditLog.objects.select_related('user').order_by('-timestamp')

        self.f_action  = self.request.GET.get('action', '').strip()
        self.f_model   = self.request.GET.get('model', '').strip()
        self.f_user    = self.request.GET.get('user', '').strip()
        self.f_date    = self.request.GET.get('date', '').strip()
        self.f_q       = self.request.GET.get('q', '').strip()

        if self.f_action:
            qs = qs.filter(action=self.f_action)
        if self.f_model:
            qs = qs.filter(model_name=self.f_model)
        if self.f_user:
            qs = qs.filter(user__username__icontains=self.f_user)
        if self.f_date:
            try:
                from datetime import date
                d = date.fromisoformat(self.f_date)
                qs = qs.filter(timestamp__date=d)
            except ValueError:
                pass
        if self.f_q:
            qs = qs.filter(object_repr__icontains=self.f_q)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['f_action'] = self.f_action
        ctx['f_model']  = self.f_model
        ctx['f_user']   = self.f_user
        ctx['f_date']   = self.f_date
        ctx['f_q']      = self.f_q
        ctx['action_choices'] = AuditLog.ACTION_CHOICES
        ctx['total_count']    = AuditLog.objects.count()
        ctx['model_choices'] = (
            AuditLog.objects.values_list('model_name', flat=True)
            .distinct().order_by('model_name')
        )
        ctx['selected_sort'] = self.request.GET.get('sort', '')
        return ctx


class AuditLogClearView(AdminRequiredMixin, View):
    """
    POST-only view. Clears audit log records.

    mode=older_than  → deletes records older than `days` days
    mode=all         → deletes every record

    Both modes require the admin's current password for confirmation.
    """
    template_name = 'audit/audit_log.html'

    def post(self, request):
        mode     = request.POST.get('clear_mode', '').strip()
        password = request.POST.get('admin_password', '').strip()
        days_raw = request.POST.get('days', '').strip()

        # Password check first
        if not password:
            messages.error(request, 'Your password is required to clear the audit trail.')
            return redirect('audit:log')

        if not request.user.check_password(password):
            messages.error(request, 'Incorrect password — audit trail not cleared.')
            return redirect('audit:log')

        if mode == 'older_than':
            try:
                days = int(days_raw)
                if days < 1:
                    raise ValueError
            except (ValueError, TypeError):
                messages.error(request, 'Please enter a valid number of days (minimum 1).')
                return redirect('audit:log')

            cutoff = timezone.now() - timedelta(days=days)
            deleted, _ = AuditLog.objects.filter(timestamp__lt=cutoff).delete()
            messages.success(
                request,
                f'{deleted:,} audit record{"s" if deleted != 1 else ""} older than '
                f'{days} day{"s" if days != 1 else ""} deleted.'
            )

        elif mode == 'all':
            deleted, _ = AuditLog.objects.all().delete()
            messages.success(
                request,
                f'All {deleted:,} audit record{"s" if deleted != 1 else ""} cleared.'
            )

        else:
            messages.error(request, 'Unknown clear mode.')

        return redirect('audit:log')
