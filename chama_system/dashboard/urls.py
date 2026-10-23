from django.urls import path
from .views import DashboardView, NotificationsView, DashboardExportPDFView

app_name = 'dashboard'

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('notifications/', NotificationsView.as_view(), name='notifications'),
    path('export/pdf/', DashboardExportPDFView.as_view(), name='export_pdf'),
]
