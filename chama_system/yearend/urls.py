from django.urls import path
from .views import YearEndListView, YearEndCreateView, YearEndDetailView

app_name = 'yearend'

urlpatterns = [
    path('', YearEndListView.as_view(), name='list'),
    path('create/', YearEndCreateView.as_view(), name='create'),
    path('<int:pk>/', YearEndDetailView.as_view(), name='detail'),
]
