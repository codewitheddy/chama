from django.urls import path
from . import views

app_name = 'penalties'

urlpatterns = [
    path('', views.PenaltyListView.as_view(), name='list'),
    path('add/', views.PenaltyCreateView.as_view(), name='add'),
    path('<int:pk>/edit/', views.PenaltyUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', views.PenaltyDeleteView.as_view(), name='delete'),
    path('<int:pk>/pay/', views.PenaltyMarkPaidView.as_view(), name='mark_paid'),
]
