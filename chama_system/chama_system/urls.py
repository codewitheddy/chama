from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import RedirectView
from django.views.static import serve
from django.conf import settings
from updater import views as views_updater

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
    path('recycle-bin/', include('recycle_bin.urls', namespace='recycle_bin')),
    path('audit/', include('audit.urls', namespace='audit')),
    path('backup/', include('backup.urls', namespace='backup')),
    path('other-income/', include('other_income.urls', namespace='other_income')),
    path('bank-accounts/', include('bank_accounts.urls', namespace='bank_accounts')),
    path('investments/', include('investments.urls', namespace='investments')),
    path('expenses/', include('expenses.urls', namespace='expenses')),
    path('money-movement/', include('money_movement.urls', namespace='money_movement')),
    path('updater/', include('updater.urls', namespace='updater')),
    path('api/client-compatibility/', views_updater.client_compatibility_api, name='client_compatibility'),
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
]
