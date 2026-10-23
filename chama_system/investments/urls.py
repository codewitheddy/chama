from django.urls import path
from . import views

app_name = 'investments'

urlpatterns = [
    # Investment Categories Management
    path('categories/', views.InvestmentCategoryListView.as_view(), name='category_list'),
    path('categories/add/', views.InvestmentCategoryCreateView.as_view(), name='category_add'),
    path('categories/<int:pk>/edit/', views.InvestmentCategoryUpdateView.as_view(), name='category_edit'),
    path('categories/<int:pk>/delete/', views.InvestmentCategoryDeleteView.as_view(), name='category_delete'),

    # Investment Types Management
    path('types/', views.InvestmentTypeListView.as_view(), name='type_list'),
    path('types/add/', views.InvestmentTypeCreateView.as_view(), name='type_add'),
    path('types/<int:pk>/edit/', views.InvestmentTypeUpdateView.as_view(), name='type_edit'),
    path('types/<int:pk>/delete/', views.InvestmentTypeDeleteView.as_view(), name='type_delete'),

    # Investment CRUD
    path('', views.InvestmentListView.as_view(), name='list'),
    path('add/', views.InvestmentCreateView.as_view(), name='add'),
    path('<int:pk>/', views.InvestmentDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.InvestmentUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', views.InvestmentDeleteView.as_view(), name='delete'),
    path('<int:pk>/approve/', views.InvestmentApprovalView.as_view(), name='approve'),

    # Valuations
    path('<int:investment_pk>/valuations/add/', views.InvestmentValuationView.as_view(), name='valuation_add'),
    path('valuations/<int:pk>/delete/', views.InvestmentValuationDeleteView.as_view(), name='valuation_delete'),

    # Returns
    path('<int:investment_pk>/returns/add/', views.InvestmentReturnView.as_view(), name='return_add'),
    path('returns/<int:pk>/delete/', views.InvestmentReturnDeleteView.as_view(), name='return_delete'),

    # Withdrawals
    path('<int:investment_pk>/withdrawals/add/', views.InvestmentWithdrawalView.as_view(), name='withdrawal_add'),
    path('withdrawals/<int:pk>/delete/', views.InvestmentWithdrawalDeleteView.as_view(), name='withdrawal_delete'),
]
