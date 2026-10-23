from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from .forms import LoginForm, UserCreateForm, UserEditForm, UserProfileForm
from .models import UserProfile
from .mixins import AdminRequiredMixin, AdminPasswordDeleteMixin

class FirstRunSetupView(View):
    """
    Shown only when the database has no users at all (fresh install).
    Creates the first admin account, then redirects to login.
    Only accessible when User.objects.count() == 0.
    """
    template_name = 'accounts/first_run.html'

    def dispatch(self, request, *args, **kwargs):
        # If users already exist, redirect to login — setup is done
        if User.objects.exists():
            return redirect('accounts:login')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        username   = request.POST.get('username', '').strip()
        password   = request.POST.get('password', '').strip()
        password2  = request.POST.get('password2', '').strip()
        group_name = request.POST.get('group_name', '').strip()
        errors = []

        if not username:
            errors.append('Username is required.')
        elif len(username) < 3:
            errors.append('Username must be at least 3 characters.')
        if not password:
            errors.append('Password is required.')
        elif len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        elif password != password2:
            errors.append('Passwords do not match.')

        if errors:
            return render(request, self.template_name, {
                'errors': errors,
                'username': username,
                'group_name': group_name,
            })

        # Create the admin user
        user = User.objects.create_superuser(
            username=username,
            password=password,
            email='',
        )
        # Profile is created by signal with role='admin'

        # Save group name if provided
        if group_name:
            try:
                from loans.models import SystemSetting
                SystemSetting.set('group_name', group_name,
                                  label='Group / Chama Name')
            except Exception:
                pass

        messages.success(
            request,
            f'Account created. Welcome, {username}! Please sign in.'
        )
        return redirect('accounts:login')



class UserLoginView(LoginView):
    form_class = LoginForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        # First-run: no users yet → go to setup
        if not User.objects.exists():
            return redirect('accounts:setup')
        return super().dispatch(request, *args, **kwargs)


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
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        user = self.get_object()
        messages.success(self.request, f"User {user.username} deleted.")
        return super().form_valid(form)


class UserUpdateRoleView(AdminRequiredMixin, UpdateView):
    model = UserProfile
    form_class = UserProfileForm
    template_name = 'accounts/user_role_form.html'
    success_url = reverse_lazy('accounts:users')

    def form_valid(self, form):
        messages.success(self.request, "Role updated.")
        return super().form_valid(form)


class MyAccountView(LoginRequiredMixin, View):
    """Allows any logged-in user to change their own password."""
    template_name = 'accounts/my_account.html'

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        current  = request.POST.get('current_password', '').strip()
        new_pw   = request.POST.get('new_password', '').strip()
        confirm  = request.POST.get('confirm_password', '').strip()
        errors   = []

        if not current:
            errors.append('Current password is required.')
        elif not request.user.check_password(current):
            errors.append('Current password is incorrect.')

        if not new_pw:
            errors.append('New password is required.')
        elif len(new_pw) < 6:
            errors.append('New password must be at least 6 characters.')
        elif new_pw != confirm:
            errors.append('New passwords do not match.')

        if errors:
            return render(request, self.template_name, {'errors': errors})

        request.user.set_password(new_pw)
        request.user.save()
        # Keep the user logged in after password change
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, request.user)
        messages.success(request, 'Password changed successfully.')
        return redirect('accounts:my_account')


class EmergencyResetView(View):
    """
    Emergency admin password reset — accessible from the login page.

    Security model:
    - Only available when running as a desktop app (DESKTOP_DB_PATH is set)
      OR when DEBUG is True. Blocked entirely on production web deployments.
    - Lists all active users so the admin can pick their account.
    - No current-password required (this is the recovery path).
    - Rate-limited to 3 attempts per session to prevent brute-force.
    """
    template_name = 'accounts/emergency_reset.html'

    def _is_allowed(self, request):
        import os
        is_desktop = bool(os.environ.get('DESKTOP_DB_PATH', ''))
        from django.conf import settings
        return is_desktop or settings.DEBUG

    def get(self, request):
        if not self._is_allowed(request):
            from django.http import Http404
            raise Http404

        # Initialise attempt counter in session
        if 'emergency_reset_attempts' not in request.session:
            request.session['emergency_reset_attempts'] = 0

        users = User.objects.filter(is_active=True).order_by('username')
        return render(request, self.template_name, {'users': users})

    def post(self, request):
        if not self._is_allowed(request):
            from django.http import Http404
            raise Http404

        # Rate limit
        attempts = request.session.get('emergency_reset_attempts', 0)
        if attempts >= 5:
            messages.error(
                request,
                'Too many reset attempts this session. Restart the app and try again.'
            )
            return redirect('accounts:emergency_reset')

        username = request.POST.get('username', '').strip()
        new_pw   = request.POST.get('new_password', '').strip()
        confirm  = request.POST.get('confirm_password', '').strip()
        users    = User.objects.filter(is_active=True).order_by('username')
        errors   = []

        if not username:
            errors.append('Please select a user.')
        if not new_pw:
            errors.append('New password is required.')
        elif len(new_pw) < 6:
            errors.append('Password must be at least 6 characters.')
        elif new_pw != confirm:
            errors.append('Passwords do not match.')

        if errors:
            request.session['emergency_reset_attempts'] = attempts + 1
            return render(request, self.template_name, {
                'users': users,
                'errors': errors,
                'selected_username': username,
            })

        try:
            user = User.objects.get(username=username, is_active=True)
        except User.DoesNotExist:
            request.session['emergency_reset_attempts'] = attempts + 1
            return render(request, self.template_name, {
                'users': users,
                'errors': [f'User "{username}" not found.'],
                'selected_username': username,
            })

        user.set_password(new_pw)
        user.save()

        # Clear the attempt counter on success
        request.session['emergency_reset_attempts'] = 0

        messages.success(
            request,
            f'Password for "{user.username}" has been reset. You can now log in.'
        )
        return redirect('accounts:login')
