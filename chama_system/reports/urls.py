from django.urls import path
from .views import (
    IncomeReportView, ContributionReportView, LoanReportView, MemberStatementView,
    ExportContributionsCSV, ExportLoansCSV, ExportPaymentsCSV, ExportMembersCSV,
)

app_name = 'reports'

urlpatterns = [
    path('income/', IncomeReportView.as_view(), name='income'),
    path('contributions/', ContributionReportView.as_view(), name='contributions'),
    path('loans/', LoanReportView.as_view(), name='loans'),
    path('member-statement/', MemberStatementView.as_view(), name='member_statement'),
    path('export/contributions/', ExportContributionsCSV.as_view(), name='export_contributions'),
    path('export/loans/', ExportLoansCSV.as_view(), name='export_loans'),
    path('export/payments/', ExportPaymentsCSV.as_view(), name='export_payments'),
    path('export/members/', ExportMembersCSV.as_view(), name='export_members'),
]
