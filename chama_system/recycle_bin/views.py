from django.views.generic import ListView, View
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth import authenticate
from django.db.models import Q
from django.utils import timezone

from accounts.mixins import AdminRequiredMixin
from .models import DeletedRecord
from .serializer import deserialize_and_restore


class RecycleBinListView(AdminRequiredMixin, ListView):
    model = DeletedRecord
    template_name = 'recycle_bin/recycle_bin_list.html'
    context_object_name = 'records'
    paginate_by = 30

    def get_queryset(self):
        qs = DeletedRecord.objects.all()
        q = self.request.GET.get('q', '').strip()
        model = self.request.GET.get('model', '').strip()
        if q:
            qs = qs.filter(
                Q(object_repr__icontains=q) |
                Q(delete_reason__icontains=q) |
                Q(deleted_by__username__icontains=q)
            )
        if model:
            qs = qs.filter(model_name__iexact=model)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_model'] = self.request.GET.get('model', '')
        ctx['model_choices'] = (
            DeletedRecord.objects
            .values_list('model_name', flat=True)
            .distinct()
            .order_by('model_name')
        )
        ctx['total_count'] = DeletedRecord.objects.count()
        return ctx


class RestoreRecordView(AdminRequiredMixin, View):
    """POST — restore a soft-deleted record back to its original table."""

    def post(self, request, pk):
        record = get_object_or_404(DeletedRecord, pk=pk)

        # Require admin password to restore
        password = request.POST.get('admin_password', '').strip()
        user = authenticate(request, username=request.user.username, password=password)
        if user is None:
            messages.error(request, "Incorrect admin password. Restore cancelled.")
            return redirect('recycle_bin:list')

        instance, error = deserialize_and_restore(record)
        if error:
            messages.error(request, f"Could not restore {record.object_repr}: {error}")
            return redirect('recycle_bin:list')

        record.delete()   # remove from recycle bin
        messages.success(request, f"Restored: {record.object_repr}")
        return redirect('recycle_bin:list')


class PermanentDeleteView(AdminRequiredMixin, View):
    """POST — permanently delete a single record from the recycle bin."""

    def post(self, request, pk):
        record = get_object_or_404(DeletedRecord, pk=pk)

        password = request.POST.get('admin_password', '').strip()
        user = authenticate(request, username=request.user.username, password=password)
        if user is None:
            messages.error(request, "Incorrect admin password. Permanent delete cancelled.")
            return redirect('recycle_bin:list')

        label = record.object_repr
        record.delete()
        messages.success(request, f"Permanently deleted: {label}")
        return redirect('recycle_bin:list')


class EmptyRecycleBinView(AdminRequiredMixin, View):
    """POST — permanently delete ALL records in the recycle bin."""

    def post(self, request):
        password = request.POST.get('admin_password', '').strip()
        user = authenticate(request, username=request.user.username, password=password)
        if user is None:
            messages.error(request, "Incorrect admin password.")
            return redirect('recycle_bin:list')

        count, _ = DeletedRecord.objects.all().delete()
        messages.success(request, f"Recycle bin emptied — {count} record(s) permanently deleted.")
        return redirect('recycle_bin:list')
