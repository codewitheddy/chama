from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display  = ('timestamp', 'user', 'action', 'model_name', 'object_repr', 'ip_address')
    list_filter   = ('action', 'app_label', 'model_name')
    search_fields = ('user__username', 'object_repr', 'ip_address')
    readonly_fields = ('timestamp', 'user', 'action', 'app_label', 'model_name',
                       'object_id', 'object_repr', 'changes', 'ip_address')
    ordering      = ('-timestamp',)

    def has_add_permission(self, request):
        return False  # audit logs are never created manually

    def has_change_permission(self, request, obj=None):
        return False  # immutable

    def has_delete_permission(self, request, obj=None):
        return False  # never delete audit records
