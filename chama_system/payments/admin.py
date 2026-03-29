from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['member', 'loan', 'amount', 'date']
    search_fields = ['member__name']
    list_filter = ['date']
