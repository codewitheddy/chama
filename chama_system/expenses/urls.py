from django.urls import path
from .views import (
    ExpenseListView, ExpenseCreateView, ExpenseUpdateView,
    ExpenseDeleteView, ExpenseDetailView, ExpenseExportView,
    ExpenseCategoryListView, ExpenseCategoryCreateView,
    ExpenseCategoryUpdateView, ExpenseCategoryDeleteView,
    RegistrationFeeFundView, RegistrationFeeFundExportView,
)

app_name = 'expenses'

urlpatterns = [
    # Expenses
    path('',                 ExpenseListView.as_view(),   name='list'),
    path('add/',             ExpenseCreateView.as_view(), name='add'),
    path('<int:pk>/',        ExpenseDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/',   ExpenseUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', ExpenseDeleteView.as_view(), name='delete'),
    path('export/',          ExpenseExportView.as_view(), name='export'),

    # Registration Fee Fund
    path('reg-fee-fund/',        RegistrationFeeFundView.as_view(),       name='reg_fee_fund'),
    path('reg-fee-fund/export/', RegistrationFeeFundExportView.as_view(), name='reg_fee_fund_export'),

    # Categories (admin)
    path('categories/',                ExpenseCategoryListView.as_view(),   name='category_list'),
    path('categories/add/',            ExpenseCategoryCreateView.as_view(), name='category_add'),
    path('categories/<int:pk>/edit/',  ExpenseCategoryUpdateView.as_view(), name='category_edit'),
    path('categories/<int:pk>/delete/',ExpenseCategoryDeleteView.as_view(), name='category_delete'),
]
