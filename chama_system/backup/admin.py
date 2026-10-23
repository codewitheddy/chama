from django.contrib import admin
from .models import BackupSetting, BackupLog


@admin.register(BackupSetting)
class BackupSettingAdmin(admin.ModelAdmin):
    list_display = ('mode', 'schedule_interval_hours', 'retention_count', 'include_media', 'last_backup_at', 'last_backup_status')
    readonly_fields = ('last_backup_at', 'last_backup_status', 'last_backup_file', 'last_backup_trigger', 'created_at', 'updated_at')


@admin.register(BackupLog)
class BackupLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'trigger_type', 'status', 'file_name', 'file_size_mb', 'duration_seconds')
    list_filter = ('trigger_type', 'status')
    search_fields = ('file_name', 'file_path', 'error_message')
    readonly_fields = ('timestamp', 'trigger_type', 'status', 'file_name', 'file_path', 'file_size_bytes', 'duration_seconds', 'error_message')
