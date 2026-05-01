from django.urls import path
from .views import MemberListView, MemberCreateView, MemberUpdateView, MemberDeleteView, MemberDetailView, MemberImportView, MemberExportView

app_name = 'members'

urlpatterns = [
    path('', MemberListView.as_view(), name='list'),
    path('add/', MemberCreateView.as_view(), name='add'),
    path('import/', MemberImportView.as_view(), name='import'),
    path('export/', MemberExportView.as_view(), name='export'),
    path('<int:pk>/edit/', MemberUpdateView.as_view(), name='edit'),
    path('<int:pk>/delete/', MemberDeleteView.as_view(), name='delete'),
    path('<int:pk>/', MemberDetailView.as_view(), name='detail'),
]
