from django.urls import path
from .views import (
    MemberListView, MemberCreateView, MemberUpdateView, MemberDeleteView, MemberDetailView,
    MemberImportView, MemberExportView, BulkMemberExitView, BulkMemberDeleteView,
    RegistrationFeePaymentAddView, RegistrationFeePaymentListView, RegistrationFeePaymentImportView,
    RegistrationFeePaymentBulkView,
    RegistrationFeeRateListView, RegistrationFeeRateCreateView, RegistrationFeeRateUpdateView
)
from .exit_views import MemberExitPreviewView, MemberExitConfirmView, MemberExitDetailView, MemberExitListView

app_name = 'members'

urlpatterns = [
    path('', MemberListView.as_view(), name='list'),
    path('add/', MemberCreateView.as_view(), name='add'),
    path('import/', MemberImportView.as_view(), name='import'),
    path('export/', MemberExportView.as_view(), name='export'),
    path('exits/', MemberExitListView.as_view(), name='exit_list'),
    path('bulk/exit/', BulkMemberExitView.as_view(), name='bulk_exit'),
    path('bulk/delete/', BulkMemberDeleteView.as_view(), name='bulk_delete'),
    path('fee-payments/', RegistrationFeePaymentListView.as_view(), name='fee_payment_list'),
    path('fee-payments/add/', RegistrationFeePaymentAddView.as_view(), name='fee_payment_add'),
    path('fee-payments/bulk/', RegistrationFeePaymentBulkView.as_view(), name='fee_payment_bulk'),
    path('fee-payments/import/', RegistrationFeePaymentImportView.as_view(), name='fee_payment_import'),
    path('fee-rate/', RegistrationFeeRateListView.as_view(), name='fee_rate_list'),
    path('fee-rate/add/', RegistrationFeeRateCreateView.as_view(), name='fee_rate_add'),
    path('fee-rate/<int:pk>/edit/', RegistrationFeeRateUpdateView.as_view(), name='fee_rate_edit'),
    path('<int:pk>/edit/', MemberUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', MemberDeleteView.as_view(), name='delete'),
    path('<int:pk>/exit/preview/', MemberExitPreviewView.as_view(), name='exit_preview'),
    path('<int:pk>/exit/confirm/', MemberExitConfirmView.as_view(), name='exit_confirm'),
    path('<int:pk>/exit/', MemberExitDetailView.as_view(), name='exit_detail'),
    path('<int:pk>/', MemberDetailView.as_view(), name='detail'),
]


