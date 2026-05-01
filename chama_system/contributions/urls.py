from django.urls import path
from .views import (
    ContributionListView, ContributionCreateView, ContributionUpdateView,
    ContributionDeleteView, ContributionDefaultersView, ContributionExportView,
    DefaultersExportView,
)

app_name = 'contributions'

urlpatterns = [
    path('', ContributionListView.as_view(), name='list'),
    path('add/', ContributionCreateView.as_view(), name='add'),
    path('export/', ContributionExportView.as_view(), name='export'),
    path('defaulters/', ContributionDefaultersView.as_view(), name='defaulters'),
    path('defaulters/export/', DefaultersExportView.as_view(), name='defaulters_export'),
    path('<int:pk>/edit/', ContributionUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', ContributionDeleteView.as_view(), name='delete'),
]
