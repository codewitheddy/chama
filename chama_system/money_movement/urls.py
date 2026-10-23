from django.urls import path
from money_movement import views

app_name = 'money_movement'

urlpatterns = [
    # Dashboard
    path('', views.MoneyMovementDashboardView.as_view(), name='dashboard'),

    # Transfers
    path('transfers/', views.MoneyTransferListView.as_view(), name='transfer_list'),
    path('transfers/add/', views.MoneyTransferCreateView.as_view(), name='transfer_add'),
    path('transfers/<int:pk>/approve/', views.MoneyTransferApproveView.as_view(), name='transfer_approve'),
    path('transfers/<int:pk>/reject/', views.MoneyTransferRejectView.as_view(), name='transfer_reject'),
    path('transfers/<int:pk>/reverse/', views.MoneyTransferReverseView.as_view(), name='transfer_reverse'),

    # Reconciliations
    path('reconciliation/cash/', views.CashReconciliationView.as_view(), name='reconcile_cash'),
    path('reconciliation/bank/', views.BankReconciliationView.as_view(), name='reconcile_bank'),

    # Reports
    path('reports/meeting-summary/', views.MeetingSummaryReportView.as_view(), name='report_meeting_summary'),
    path('reports/cash-book/', views.CashBookReportView.as_view(), name='report_cash_book'),
    path('reports/bank-ledger/', views.BankLedgerReportView.as_view(), name='report_bank_ledger'),
    path('reports/income-vs-expenses/', views.IncomeVsExpensesReportView.as_view(), name='report_income_vs_expenses'),
    path('reports/investments/', views.InvestmentRegisterReportView.as_view(), name='report_investments'),
    path('reports/funds-position/', views.FundsPositionReportView.as_view(), name='report_funds_position'),
]
