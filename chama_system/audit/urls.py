from django.urls import path
from .views import AuditLogListView, AuditLogClearView

app_name = 'audit'

urlpatterns = [
    path('', AuditLogListView.as_view(), name='log'),
    path('clear/', AuditLogClearView.as_view(), name='clear'),
]
