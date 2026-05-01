from django.urls import path
from .views import (
    WelfareDashboardView,
    WelfareContributionRateView,
    WelfareContributionListView,
    WelfareContributionCreateView,
    WelfareContributionUpdateView,
    WelfareContributionDeleteView,
    WelfareContributionExportView,
    WelfareDefaultersView,
    WelfareDefaultersExportView,
    WelfareEventListView,
    WelfareEventCreateView,
    WelfareEventUpdateView,
    WelfareEventDeleteView,
    WelfareEventDetailView,
    WelfareEventCloseView,
    WelfareEventExportView,
    WelfareDisbursementCreateView,
    WelfareDisbursementUpdateView,
    WelfareDisbursementDeleteView,
    WelfareSupportCreateView,
    WelfareSupportUpdateView,
    WelfareSupportDeleteView,
)

app_name = 'welfare'

urlpatterns = [
    # Dashboard
    path('', WelfareDashboardView.as_view(), name='dashboard'),

    # Contribution rate
    path('rate/', WelfareContributionRateView.as_view(), name='rate'),

    # Welfare contributions
    path('contributions/', WelfareContributionListView.as_view(), name='contribution_list'),
    path('contributions/add/', WelfareContributionCreateView.as_view(), name='contribution_add'),
    path('contributions/export/', WelfareContributionExportView.as_view(), name='contribution_export'),
    path('contributions/defaulters/', WelfareDefaultersView.as_view(), name='defaulters'),
    path('contributions/defaulters/export/', WelfareDefaultersExportView.as_view(), name='defaulters_export'),
    path('contributions/<int:pk>/edit/', WelfareContributionUpdateView.as_view(), name='contribution_edit'),
    path('contributions/<int:pk>/delete/', WelfareContributionDeleteView.as_view(), name='contribution_delete'),

    # Welfare events
    path('events/', WelfareEventListView.as_view(), name='event_list'),
    path('events/add/', WelfareEventCreateView.as_view(), name='event_add'),
    path('events/<int:pk>/', WelfareEventDetailView.as_view(), name='event_detail'),
    path('events/<int:pk>/edit/', WelfareEventUpdateView.as_view(), name='event_edit'),
    path('events/<int:pk>/delete/', WelfareEventDeleteView.as_view(), name='event_delete'),
    path('events/<int:pk>/close/', WelfareEventCloseView.as_view(), name='event_close'),
    path('events/<int:pk>/export/', WelfareEventExportView.as_view(), name='event_export'),

    # Disbursements (nested under event)
    path('events/<int:pk>/disbursement/add/', WelfareDisbursementCreateView.as_view(), name='disbursement_add'),
    path('disbursement/<int:pk>/edit/', WelfareDisbursementUpdateView.as_view(), name='disbursement_edit'),
    path('disbursement/<int:pk>/delete/', WelfareDisbursementDeleteView.as_view(), name='disbursement_delete'),

    # Support contributions (nested under event)
    path('events/<int:pk>/support/add/', WelfareSupportCreateView.as_view(), name='support_add'),
    path('support/<int:pk>/edit/', WelfareSupportUpdateView.as_view(), name='support_edit'),
    path('support/<int:pk>/delete/', WelfareSupportDeleteView.as_view(), name='support_delete'),
]
