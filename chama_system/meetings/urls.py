from django.urls import path
from . import views

app_name = 'meetings'

urlpatterns = [
    path('', views.MeetingListView.as_view(), name='list'),
    path('add/', views.MeetingCreateView.as_view(), name='add'),
    path('<int:pk>/', views.MeetingDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.MeetingUpdateView.as_view(), name='edit'),
    path('<int:pk>/edit-minutes/', views.MeetingUpdateMinutesView.as_view(), name='edit_minutes'),
    path('<int:pk>/minutes/', views.MeetingMinutesView.as_view(), name='minutes'),
    path('<int:pk>/minutes/docx/', views.MeetingMinutesDocxView.as_view(), name='minutes_docx'),
    path('<int:pk>/delete/', views.MeetingDeleteView.as_view(), name='delete'),
    path('<int:pk>/attendance/', views.SaveAttendanceView.as_view(), name='save_attendance'),
    path('<int:pk>/penalty/add/', views.AddMeetingPenaltyView.as_view(), name='add_penalty'),
    path('penalty/<int:pk>/delete/', views.DeleteMeetingPenaltyView.as_view(), name='delete_penalty'),
    path('rules/', views.PenaltyRuleListView.as_view(), name='rules'),
    path('rules/add/', views.PenaltyRuleCreateView.as_view(), name='rule_add'),
    path('rules/<int:pk>/edit/', views.PenaltyRuleUpdateView.as_view(), name='rule_edit'),
    path('rules/<int:pk>/delete/', views.PenaltyRuleDeleteView.as_view(), name='rule_delete'),
]
