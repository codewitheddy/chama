from django.urls import path
from .views import (
    LoanListView, LoanCreateView, LoanUpdateView,
    LoanDeleteView, LoanDetailView, LoanCalculatorView,
    CollateralCreateView, CollateralDeleteView,
    GuarantorAddView, GuarantorDeleteView, GuarantorsReportView,
    MemberContributionCheckView, LoanRolloverView, LoanExportView,
    LoanSettingsView, GroupSettingsView,
    LoanProductListView, LoanProductCreateView, LoanProductUpdateView,
    LoanProductDeleteView, LoanProductDetailAPIView,
    NonMemberApplicantListView, NonMemberApplicantCreateView,
    NonMemberApplicantDetailView, NonMemberApplicantUpdateView,
    NonMemberApplicantDeleteView, NonMemberQualifyView,
    LoanApplicationListView, LoanApplicationCreateView,
    LoanApplicationDetailView, LoanApplicationDeleteView,
    LoanRestructureListView, LoanRestructureRequestView,
    LoanRestructureDetailView, LoanRestructureApproveView,
    LoanRestructureRejectView, LoanRestructurePreviewAPIView,
)

app_name = 'loans'

urlpatterns = [
    # ── Loans ─────────────────────────────────────────────────────
    path('', LoanListView.as_view(), name='list'),
    path('add/', LoanCreateView.as_view(), name='add'),
    path('export/', LoanExportView.as_view(), name='export'),
    path('<int:pk>/', LoanDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', LoanUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', LoanDeleteView.as_view(), name='delete'),
    path('<int:pk>/rollover/', LoanRolloverView.as_view(), name='rollover'),
    path('calculator/', LoanCalculatorView.as_view(), name='calculator'),
    path('member-check/', MemberContributionCheckView.as_view(), name='member_check'),

    # ── Loan Applications ─────────────────────────────────────────
    path('applications/', LoanApplicationListView.as_view(), name='applications'),
    path('applications/add/', LoanApplicationCreateView.as_view(), name='application_new'),
    path('applications/<int:pk>/', LoanApplicationDetailView.as_view(), name='application_detail'),
    path('applications/<int:pk>/delete/', LoanApplicationDeleteView.as_view(), name='application_delete'),

    # ── Collateral & Guarantors ───────────────────────────────────
    path('<int:loan_pk>/collateral/add/', CollateralCreateView.as_view(), name='collateral_add'),
    path('collateral/<int:pk>/delete/', CollateralDeleteView.as_view(), name='collateral_delete'),
    path('<int:loan_pk>/guarantor/add/', GuarantorAddView.as_view(), name='guarantor_add'),
    path('guarantor/<int:pk>/delete/', GuarantorDeleteView.as_view(), name='guarantor_delete'),
    path('guarantors/', GuarantorsReportView.as_view(), name='guarantors_report'),

    # ── Loan Products ─────────────────────────────────────────────
    path('products/', LoanProductListView.as_view(), name='product_list'),
    path('products/add/', LoanProductCreateView.as_view(), name='product_add'),
    path('products/<int:pk>/edit/', LoanProductUpdateView.as_view(), name='product_edit'),
    path('products/<int:pk>/delete/', LoanProductDeleteView.as_view(), name='product_delete'),
    path('products/<int:pk>/api/', LoanProductDetailAPIView.as_view(), name='product_api'),

    # ── Non-Member Applicants ─────────────────────────────────────
    path('non-members/', NonMemberApplicantListView.as_view(), name='non_members'),
    path('non-members/add/', NonMemberApplicantCreateView.as_view(), name='non_member_add'),
    path('non-members/<int:pk>/', NonMemberApplicantDetailView.as_view(), name='non_member_detail'),
    path('non-members/<int:pk>/edit/', NonMemberApplicantUpdateView.as_view(), name='non_member_edit'),
    path('non-members/<int:pk>/delete/', NonMemberApplicantDeleteView.as_view(), name='non_member_delete'),
    path('non-members/<int:pk>/qualify/', NonMemberQualifyView.as_view(), name='non_member_qualify'),

    # ── Settings ──────────────────────────────────────────────────
    path('settings/', LoanSettingsView.as_view(), name='settings'),
    path('group-settings/', GroupSettingsView.as_view(), name='group_settings'),

    # ── Loan Restructuring ────────────────────────────────────────
    path('restructures/', LoanRestructureListView.as_view(), name='restructure_list'),
    path('<int:loan_pk>/restructure/add/', LoanRestructureRequestView.as_view(), name='restructure_add'),
    path('restructures/<int:pk>/', LoanRestructureDetailView.as_view(), name='restructure_detail'),
    path('restructures/<int:pk>/approve/', LoanRestructureApproveView.as_view(), name='restructure_approve'),
    path('restructures/<int:pk>/reject/', LoanRestructureRejectView.as_view(), name='restructure_reject'),
    path('<int:loan_pk>/restructure/preview-api/', LoanRestructurePreviewAPIView.as_view(), name='restructure_preview_api'),
]


