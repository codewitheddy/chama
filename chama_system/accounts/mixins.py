from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class AdminPasswordDeleteMixin:
    """
    Mixin for DeleteViews that:
      1. Requires a non-empty deletion reason
      2. Requires the current admin user's password
      3. Saves a soft-delete snapshot to the recycle bin before deleting

    Add this BEFORE AdminRequiredMixin in the MRO, e.g.:
        class MyDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    """
    delete_reason_field = 'delete_reason'
    delete_password_field = 'admin_password'

    def post(self, request, *args, **kwargs):
        reason = request.POST.get(self.delete_reason_field, '').strip()
        password = request.POST.get(self.delete_password_field, '').strip()

        if not reason:
            return self._render_with_error(request, "A reason for deletion is required.", reason, *args, **kwargs)

        if not request.user.check_password(password):
            return self._render_with_error(request, "Incorrect password. Deletion cancelled.", reason, *args, **kwargs)

        # Save to recycle bin before the actual delete
        self._save_to_recycle_bin(request, reason)

        return super().post(request, *args, **kwargs)

    def _render_with_error(self, request, error_msg, reason='', *args, **kwargs):
        """Re-render the confirmation page with an inline error — no messages framework."""
        from django.shortcuts import render as django_render
        self.object = self.get_object()
        ctx = self.get_context_data(
            object=self.object,
            delete_error=error_msg,
            delete_reason_value=reason,
        )
        return django_render(request, self.get_template_names()[0], ctx)

    def _save_to_recycle_bin(self, request, reason):
        from recycle_bin.models import DeletedRecord
        from recycle_bin.serializer import serialize_instance

        obj = self.get_object()
        try:
            data = serialize_instance(obj)
            DeletedRecord.objects.create(
                app_label=obj._meta.app_label,
                model_name=obj._meta.model_name,
                object_id=str(obj.pk),
                object_repr=str(obj)[:300],
                data=data,
                delete_reason=reason,
                deleted_by=request.user,
            )
        except Exception:
            # Never block a delete because of recycle bin failure
            pass


class RoleRequiredMixin(LoginRequiredMixin):
    """Base mixin — override allowed_roles in subclass."""
    allowed_roles = ('admin', 'treasurer', 'readonly')

    def dispatch(self, request, *args, **kwargs):
        # Let LoginRequiredMixin handle unauthenticated users first
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)
        # Now check role
        profile = getattr(request.user, 'profile', None)
        if profile is None or profile.role not in self.allowed_roles:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(RoleRequiredMixin):
    allowed_roles = ('admin',)


class TreasurerRequiredMixin(RoleRequiredMixin):
    allowed_roles = ('admin', 'treasurer')


class MemberAccessMixin(RoleRequiredMixin):
    """Read access for all authenticated roles — blocks unauthenticated only.
    Use on detail/list views that show financial data."""
    allowed_roles = ('admin', 'treasurer', 'readonly')
