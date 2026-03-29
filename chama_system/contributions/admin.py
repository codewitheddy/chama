from django.contrib import admin
from .models import Contribution


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):
    list_display = ['member', 'amount', 'month', 'year', 'date']
    list_filter = ['month', 'year']
    search_fields = ['member__name']
