from django.urls import path
from .views import (
    IncomeReportView, ContributionReportView, LoanReportView, MemberStatementView,
    ExportContributionsCSV, ExportLoansCSV, ExportPaymentsCSV, ExportMembersCSV,
    ExportContributionsPDF, ExportLoansPDF, ExportIncomePDF,
    ExportMemberStatementCSV, ExportMemberStatementPDF,
)

app_name = 'reports'

urlpatterns = [
    path('income/', IncomeReportView.as_view(), name='income'),
    path('contributions/', ContributionReportView.as_view(), name='contributions'),
    path('loans/', LoanReportView.as_view(), name='loans'),
    path('member-statement/', MemberStatementView.as_view(), name='member_statement'),
    # CSV
    path('export/contributions/', ExportContributionsCSV.as_view(), name='export_contributions'),
    path('export/loans/', ExportLoansCSV.as_view(), name='export_loans'),
    path('export/payments/', ExportPaymentsCSV.as_view(), name='export_payments'),
    path('export/members/', ExportMembersCSV.as_view(), name='export_members'),
    path('export/member-statement/csv/', ExportMemberStatementCSV.as_view(), name='export_member_statement_csv'),
    # PDF
    path('export/contributions/pdf/', ExportContributionsPDF.as_view(), name='export_contributions_pdf'),
    path('export/loans/pdf/', ExportLoansPDF.as_view(), name='export_loans_pdf'),
    path('export/income/pdf/', ExportIncomePDF.as_view(), name='export_income_pdf'),
    path('export/member-statement/pdf/', ExportMemberStatementPDF.as_view(), name='export_member_statement_pdf'),
]
