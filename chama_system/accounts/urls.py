from django.urls import path
from .views import (
    UserLoginView, UserLogoutView, UserListView, UserCreateView,
    UserEditView, UserDeleteView, UserUpdateRoleView, FirstRunSetupView,
    MyAccountView, EmergencyResetView,
)

app_name = 'accounts'

urlpatterns = [
    path('setup/', FirstRunSetupView.as_view(), name='setup'),
    path('login/', UserLoginView.as_view(), name='login'),
    path('logout/', UserLogoutView.as_view(), name='logout'),
    path('me/', MyAccountView.as_view(), name='my_account'),
    path('emergency-reset/', EmergencyResetView.as_view(), name='emergency_reset'),
    path('users/', UserListView.as_view(), name='users'),
    path('users/add/', UserCreateView.as_view(), name='user_add'),
    path('users/<int:pk>/edit/', UserEditView.as_view(), name='user_edit'),
    path('users/<int:pk>/delete/', UserDeleteView.as_view(), name='user_delete'),
    path('users/<int:pk>/role/', UserUpdateRoleView.as_view(), name='user_role'),
]
