from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(LoginRequiredMixin):
    """Base mixin — override allowed_roles in subclass."""
    allowed_roles = ('admin', 'treasurer', 'readonly')

    def dispatch(self, request, *args, **kwargs):
        # Let LoginRequiredMixin handle unauthenticated users first
        if not request.user.is_authenticated:
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
