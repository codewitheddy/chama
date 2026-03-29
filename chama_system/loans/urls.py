from django.urls import path
from .views import (
    LoanListView, LoanCreateView, LoanUpdateView,
    LoanDeleteView, LoanDetailView, LoanCalculatorView,
    CollateralCreateView, CollateralDeleteView,
    GuarantorAddView, GuarantorDeleteView, GuarantorsReportView,
    MemberContributionCheckView, LoanRolloverView,
)

app_name = 'loans'

urlpatterns = [
    path('', LoanListView.as_view(), name='list'),
    path('add/', LoanCreateView.as_view(), name='add'),
    path('<int:pk>/', LoanDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', LoanUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', LoanDeleteView.as_view(), name='delete'),
    path('<int:pk>/rollover/', LoanRolloverView.as_view(), name='rollover'),
    path('calculator/', LoanCalculatorView.as_view(), name='calculator'),
    path('member-check/', MemberContributionCheckView.as_view(), name='member_check'),
    path('<int:loan_pk>/collateral/add/', CollateralCreateView.as_view(), name='collateral_add'),
    path('collateral/<int:pk>/delete/', CollateralDeleteView.as_view(), name='collateral_delete'),
    path('<int:loan_pk>/guarantor/add/', GuarantorAddView.as_view(), name='guarantor_add'),
    path('guarantor/<int:pk>/delete/', GuarantorDeleteView.as_view(), name='guarantor_delete'),
    path('guarantors/', GuarantorsReportView.as_view(), name='guarantors_report'),
]
