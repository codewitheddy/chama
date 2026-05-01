from django.urls import path
from .views import PaymentListView, PaymentCreateView, PaymentDeleteView, PaymentExportView

app_name = 'payments'

urlpatterns = [
    path('', PaymentListView.as_view(), name='list'),
    path('add/', PaymentCreateView.as_view(), name='add'),
    path('export/', PaymentExportView.as_view(), name='export'),
    path('<int:pk>/delete/', PaymentDeleteView.as_view(), name='delete'),
]
