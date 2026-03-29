from django.contrib import admin
from .models import Member


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'registration_fee', 'date_joined']
    search_fields = ['name', 'phone']
    list_filter = ['date_joined']
