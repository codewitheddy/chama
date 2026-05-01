from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from .forms import LoginForm, UserCreateForm, UserEditForm, UserProfileForm
from .models import UserProfile
from .mixins import AdminRequiredMixin, AdminPasswordDeleteMixin


class UserLoginView(LoginView):
    form_class = LoginForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True


class UserLogoutView(LogoutView):
    next_page = reverse_lazy('accounts:login')


class UserListView(AdminRequiredMixin, ListView):
    model = User
    template_name = 'accounts/user_list.html'
    context_object_name = 'users'
    queryset = User.objects.select_related('profile').all()


class UserCreateView(AdminRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = 'accounts/user_form.html'
    success_url = reverse_lazy('accounts:users')

    def form_valid(self, form):
        response = super().form_valid(form)
        role = form.cleaned_data.get('role', 'readonly')
        profile, _ = UserProfile.objects.get_or_create(user=self.object)
        profile.role = role
        profile.save()
        messages.success(self.request, f"User {self.object.username} created.")
        return response


class UserEditView(AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserEditForm
    template_name = 'accounts/user_edit_form.html'
    success_url = reverse_lazy('accounts:users')

    def get_object(self, queryset=None):
        return get_object_or_404(User, pk=self.kwargs['pk'])

    def form_valid(self, form):
        # prevent admin from deactivating themselves
        if form.instance == self.request.user and not form.cleaned_data.get('is_active', True):
            messages.error(self.request, "You cannot deactivate your own account.")
            return self.form_invalid(form)
        messages.success(self.request, f"User {form.instance.username} updated.")
        return super().form_valid(form)


class UserDeleteView(AdminPasswordDeleteMixin, AdminRequiredMixin, DeleteView):
    model = User
    template_name = 'accounts/user_confirm_delete.html'
    success_url = reverse_lazy('accounts:users')

    def get_object(self, queryset=None):
        return get_object_or_404(User, pk=self.kwargs['pk'])

    def post(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            messages.error(request, "You cannot delete your own account.")
            return redirect('accounts:users')
        messages.success(request, f"User {user.username} deleted.")
        return super().post(request, *args, **kwargs)


class UserUpdateRoleView(AdminRequiredMixin, UpdateView):
    model = UserProfile
    form_class = UserProfileForm
    template_name = 'accounts/user_role_form.html'
    success_url = reverse_lazy('accounts:users')

    def form_valid(self, form):
        messages.success(self.request, "Role updated.")
        return super().form_valid(form)
