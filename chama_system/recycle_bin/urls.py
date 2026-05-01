from django.urls import path
from . import views

app_name = 'recycle_bin'

urlpatterns = [
    path('', views.RecycleBinListView.as_view(), name='list'),
    path('<int:pk>/restore/', views.RestoreRecordView.as_view(), name='restore'),
    path('<int:pk>/delete/', views.PermanentDeleteView.as_view(), name='permanent_delete'),
    path('empty/', views.EmptyRecycleBinView.as_view(), name='empty'),
]
