from django.contrib import admin
from .models import (
    WelfareContributionRate, WelfareContribution, WelfareEvent,
    WelfareDisbursement, WelfareSupportContribution,
)


@admin.register(WelfareContributionRate)
class WelfareContributionRateAdmin(admin.ModelAdmin):
    list_display = ('amount', 'effective_date', 'created_at')
    list_filter = ('effective_date',)
    ordering = ('-effective_date',)


@admin.register(WelfareContribution)
class WelfareContributionAdmin(admin.ModelAdmin):
    list_display = ('member', 'amount', 'month', 'year', 'date')
    list_filter = ('month', 'year')
    search_fields = ('member__name',)
    ordering = ('-date',)


@admin.register(WelfareEvent)
class WelfareEventAdmin(admin.ModelAdmin):
    list_display = ('pk', 'beneficiary', 'date_opened', 'status')
    list_filter = ('status',)
    search_fields = ('beneficiary__name', 'description')
    ordering = ('-date_opened',)


@admin.register(WelfareDisbursement)
class WelfareDisbursementAdmin(admin.ModelAdmin):
    list_display = ('pk', 'event', 'amount', 'date')
    search_fields = ('event__beneficiary__name',)
    ordering = ('-date',)


@admin.register(WelfareSupportContribution)
class WelfareSupportContributionAdmin(admin.ModelAdmin):
    list_display = ('contributor', 'event', 'amount', 'date')
    search_fields = ('contributor__name', 'event__beneficiary__name')
    ordering = ('-date',)
