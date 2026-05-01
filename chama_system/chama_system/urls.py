from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', RedirectView.as_view(url='/dashboard/', permanent=False)),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('members/', include('members.urls')),
    path('contributions/', include('contributions.urls')),
    path('loans/', include('loans.urls')),
    path('payments/', include('payments.urls')),
    path('reports/', include('reports.urls')),
    path('penalties/', include('penalties.urls')),
    path('meetings/', include('meetings.urls')),
    path('welfare/', include('welfare.urls')),
    path('yearend/', include('yearend.urls', namespace='yearend')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
