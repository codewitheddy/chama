"""
URL patterns for the updater app.
"""

from django.urls import path
from . import views

app_name = "updater"

urlpatterns = [
    path("check/", views.check_updates_api, name="check"),
    path("download/", views.start_download_api, name="download"),
    path("progress/", views.download_progress_api, name="progress"),
    path("install/", views.install_update_api, name="install"),
    path("skip/", views.skip_version_api, name="skip"),
    path("remind-later/", views.remind_later_api, name="remind_later"),
    path("safety-check/", views.transaction_safety_api, name="safety_check"),
    path("client-compatibility/", views.client_compatibility_api, name="compatibility"),
]
