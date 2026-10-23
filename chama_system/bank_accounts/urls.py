from django.urls import path
from .views import (
    BankAccountListView, BankAccountCreateView,
    BankAccountUpdateView, BankAccountDeleteView,
    BankAccountDetailView,
    BankBalanceCreateView, BankBalanceDeleteView,
    BankTopUpView, BankOpeningBalanceView,
    BulkBankAccountDeleteView,
)

app_name = 'bank_accounts'

urlpatterns = [
    path('',                              BankAccountListView.as_view(),    name='list'),
    path('add/',                          BankAccountCreateView.as_view(),  name='add'),
    path('bulk-delete/',                  BulkBankAccountDeleteView.as_view(), name='bulk_delete'),
    path('<int:pk>/',                     BankAccountDetailView.as_view(),  name='detail'),
    path('<int:pk>/edit/',                BankAccountUpdateView.as_view(),  name='edit'),
    path('<int:pk>/delete/',              BankAccountDeleteView.as_view(),  name='delete'),
    # New: top-up and opening balance
    path('<int:account_pk>/topup/',       BankTopUpView.as_view(),          name='topup'),
    path('<int:account_pk>/opening/',     BankOpeningBalanceView.as_view(), name='opening_balance'),
    # Legacy snapshot
    path('<int:account_pk>/balance/add/', BankBalanceCreateView.as_view(),  name='balance_add'),
    path('balance/<int:pk>/delete/',      BankBalanceDeleteView.as_view(),  name='balance_delete'),
]
