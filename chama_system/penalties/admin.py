from django.contrib import admin
from .models import Penalty


@admin.register(Penalty)
class PenaltyAdmin(admin.ModelAdmin):
    list_display = ['member', 'amount', 'date', 'reason']
    list_filter = ['date']
    search_fields = ['member__name', 'reason']
