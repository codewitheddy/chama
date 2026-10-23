from django.urls import path
from .views import (
    YearEndListView, YearEndCreateView, YearEndDetailView,
    YearEndExportPDFView, YearEndPreviewView, YearEndPreviewPDFView,
)

app_name = 'yearend'

urlpatterns = [
    path('', YearEndListView.as_view(), name='list'),
    path('preview/', YearEndPreviewView.as_view(), name='preview'),
    path('preview/pdf/', YearEndPreviewPDFView.as_view(), name='preview_pdf'),
    path('create/', YearEndCreateView.as_view(), name='create'),
    path('<int:pk>/', YearEndDetailView.as_view(), name='detail'),
    path('<int:pk>/export/pdf/', YearEndExportPDFView.as_view(), name='export_pdf'),
]
