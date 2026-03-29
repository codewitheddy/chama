from django.contrib import admin
from .models import Meeting, MeetingAttendance, MeetingPenalty, MeetingPenaltyRule


@admin.register(MeetingPenaltyRule)
class MeetingPenaltyRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'default_amount', 'description']


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ['date', 'venue', 'status']
    list_filter = ['status']


@admin.register(MeetingAttendance)
class MeetingAttendanceAdmin(admin.ModelAdmin):
    list_display = ['meeting', 'member', 'status']


@admin.register(MeetingPenalty)
class MeetingPenaltyAdmin(admin.ModelAdmin):
    list_display = ['meeting', 'member', 'rule', 'amount', 'reason']
