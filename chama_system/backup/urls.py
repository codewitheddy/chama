from django.urls import path
from .views import BackupView, DownloadLocalBackupView, ValidateDirectoryAPIView

app_name = 'backup'

urlpatterns = [
    path('', BackupView.as_view(), name='backup'),
    path('download/<str:filename>/', DownloadLocalBackupView.as_view(), name='download_local'),
    path('api/validate-directory/', ValidateDirectoryAPIView.as_view(), name='validate_directory'),
]
