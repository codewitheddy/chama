from django.contrib import admin
from .models import YearEndWithdrawal, MemberInterestShare, YearEndMemberStatus


@admin.register(YearEndWithdrawal)
class YearEndWithdrawalAdmin(admin.ModelAdmin):
    list_display = ('financial_year', 'date', 'amount_withdrawn', 'interest_shared', 'recorded_by')
    list_filter = ('financial_year',)
    ordering = ('-financial_year',)
    readonly_fields = ('recorded_by', 'created_at')


@admin.register(MemberInterestShare)
class MemberInterestShareAdmin(admin.ModelAdmin):
    list_display = ('member', 'withdrawal', 'amount')
    list_filter = ('withdrawal__financial_year',)
    search_fields = ('member__name',)


@admin.register(YearEndMemberStatus)
class YearEndMemberStatusAdmin(admin.ModelAdmin):
    list_display = ('member', 'withdrawal', 'status')
    list_filter = ('status', 'withdrawal__financial_year')
    search_fields = ('member__name',)
