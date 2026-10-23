from django.urls import path
from .views import (
    OtherIncomeListView,
    OtherIncomeCreateView,
    OtherIncomeUpdateView,
    OtherIncomeDeleteView,
    OtherIncomeReconcileToggleView,
)

app_name = 'other_income'

urlpatterns = [
    path('', OtherIncomeListView.as_view(), name='list'),
    path('add/', OtherIncomeCreateView.as_view(), name='add'),
    path('<int:pk>/edit/', OtherIncomeUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', OtherIncomeDeleteView.as_view(), name='delete'),
    path('<int:pk>/reconcile-toggle/', OtherIncomeReconcileToggleView.as_view(), name='reconcile_toggle'),
]
