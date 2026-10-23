"""
Backup & Restore views.

Provides:
- Comprehensive backup configuration (Manual, Automatic - system decides, Scheduled - admin decides).
- Custom storage directory management with validation.
- Direct browser downloads and local filesystem snapshot generation.
- Stored backup file manager (List, Download, Restore, Delete).
- Safe atomic restoration with active admin preservation.
"""

import io
import os
import shutil
import zipfile
import tempfile
import datetime
import subprocess
from pathlib import Path
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse, Http404
from django.shortcuts import render, redirect
from django.views import View
from django.utils import timezone

from accounts.mixins import AdminRequiredMixin
from .models import BackupSetting, BackupLog
from .services import (
    db_conf, is_sqlite, sqlite_path, media_root,
    build_backup_zip, get_system_default_backup_dir,
    get_configured_backup_dir, validate_backup_directory,
    create_backup_file, list_local_backups, delete_local_backup
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _auto_save_current_db(label='pre_restore') -> Path | None:
    """
    Before restoring, save the current DB to the user's Documents or AppData
    so it is not lost. Returns the path where it was saved, or None.
    """
    if not is_sqlite():
        return None
    db_p = sqlite_path()
    if not db_p.exists():
        return None
    try:
        docs = Path(os.environ.get('USERPROFILE', Path.home())) / 'Documents' / 'FinanceWiseTBM_backups' / 'safety'
        docs.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        dest = docs / f"safety_{label}_{ts}.sqlite3"
        shutil.copy2(db_p, dest)
        return dest
    except Exception:
        return None


# ── views ────────────────────────────────────────────────────────────────────

class BackupView(AdminRequiredMixin, View):
    template_name = 'backup/backup.html'

    def get(self, request):
        ctx = self._context()
        # Pick up restore result passed via query params (session may not survive a DB swap)
        if request.GET.get('restored'):
            saved_to = request.GET.get('saved_to', '')
            preserved_admin = request.GET.get('preserved_admin', '')
            app_ver = getattr(settings, 'APP_VERSION', '1.1.0')
            msg = f"Data restored successfully and upgraded to v{app_ver}! All latest features, bank account segregations, and system updates are active."
            if preserved_admin:
                msg += f" Your admin account '{preserved_admin}' was preserved."
            if saved_to:
                msg += f' A safety copy of the previous database was saved to: {saved_to}'
            messages.success(request, msg)
        elif request.GET.get('error'):
            messages.error(request, f"Restore failed: {request.GET.get('error')}")
        return render(request, self.template_name, ctx)

    def post(self, request):
        action = request.POST.get('action', '')

        if action == 'save_settings':
            return self._handle_save_settings(request)

        if action == 'download':
            return self._handle_download(request)

        if action == 'create_local':
            return self._handle_create_local(request)

        if action == 'restore_upload':
            return self._handle_restore_upload(request)

        if action == 'restore_local':
            return self._handle_restore_local(request)

        if action == 'restore_confirm':
            return self._handle_restore_confirm(request)

        if action == 'delete_local':
            return self._handle_delete_local(request)

        messages.error(request, 'Unknown action.')
        return redirect('backup:backup')

    # ── settings ─────────────────────────────────────────────────

    def _handle_save_settings(self, request):
        setting = BackupSetting.get_settings()
        mode = request.POST.get('mode', 'manual').strip().lower()
        if mode not in ['manual', 'automatic', 'scheduled']:
            mode = 'manual'

        custom_location = request.POST.get('custom_location', '').strip()
        schedule_interval = request.POST.get('schedule_interval_hours', '24').strip()
        retention = request.POST.get('retention_count', '15').strip()
        include_media = request.POST.get('include_media') == 'on' or request.POST.get('include_media') == 'true'

        try:
            interval_int = max(1, int(schedule_interval))
        except ValueError:
            interval_int = 24

        try:
            retention_int = max(0, int(retention))
        except ValueError:
            retention_int = 15

        # Validate custom directory if in scheduled mode
        if mode == 'scheduled' and custom_location:
            valid, msg, norm_path = validate_backup_directory(custom_location)
            if not valid:
                messages.error(request, f"Invalid storage location: {msg}")
                return redirect('backup:backup')
            custom_location = norm_path

        setting.mode = mode
        setting.custom_location = custom_location
        setting.schedule_interval_hours = interval_int
        setting.retention_count = retention_int
        setting.include_media = include_media
        setting.save()

        mode_name = dict(BackupSetting.MODE_CHOICES).get(mode, mode.capitalize())
        messages.success(request, f"Backup settings updated successfully. Active mode: {mode_name}.")
        return redirect('backup:backup')

    # ── download ─────────────────────────────────────────────────

    def _handle_download(self, request):
        try:
            setting = BackupSetting.get_settings()
            buf = build_backup_zip(include_media=setting.include_media)
            now = timezone.localtime(timezone.now())
            filename = f"backup_download_{now.strftime('%Y%m%d_%H%M%S')}.zip"
            response = HttpResponse(buf, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except Exception as exc:
            messages.error(request, f'Backup download failed: {exc}')
            return redirect('backup:backup')

    # ── create local snapshot ────────────────────────────────────

    def _handle_create_local(self, request):
        setting = BackupSetting.get_settings()
        success, msg, _ = create_backup_file(
            trigger='manual',
            include_media=setting.include_media
        )
        if success:
            messages.success(request, msg)
        else:
            messages.error(request, msg)
        return redirect('backup:backup')

    # ── delete local snapshot ────────────────────────────────────

    def _handle_delete_local(self, request):
        filename = request.POST.get('filename', '').strip()
        if not filename:
            messages.error(request, "No filename specified for deletion.")
            return redirect('backup:backup')

        success, msg = delete_local_backup(filename)
        if success:
            messages.success(request, msg)
        else:
            messages.error(request, msg)
        return redirect('backup:backup')

    # ── restore: from uploaded file ──────────────────────────────

    def _handle_restore_upload(self, request):
        uploaded = request.FILES.get('backup_file')
        if not uploaded:
            messages.error(request, 'Please choose a backup file to upload.')
            return redirect('backup:backup')

        if not uploaded.name.endswith('.zip'):
            messages.error(request, 'Only .zip backup files are accepted.')
            return redirect('backup:backup')

        try:
            data = uploaded.read()
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                has_sqlite = 'db.sqlite3' in names
                has_json   = 'data.json' in names
                has_pgdump = 'db.dump' in names

                if is_sqlite() and not has_sqlite:
                    messages.error(
                        request,
                        'This backup does not contain a db.sqlite3 file. '
                        'It may be from a PostgreSQL installation.'
                    )
                    return redirect('backup:backup')

                if not is_sqlite() and not has_json and not has_pgdump:
                    messages.error(
                        request,
                        'This backup does not contain data.json or db.dump. '
                        'The file may be corrupted.'
                    )
                    return redirect('backup:backup')

            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.zip', prefix='fwtbm_restore_')
            try:
                with os.fdopen(tmp_fd, 'wb') as f:
                    f.write(data)
            except Exception:
                os.unlink(tmp_path)
                raise

            request.session['pending_restore_path'] = tmp_path
            request.session['pending_restore_name'] = uploaded.name

            file_count = len(names)
            ctx = self._context()
            ctx.update({
                'confirm_restore': True,
                'restore_filename': uploaded.name,
                'restore_file_count': file_count,
            })
            return render(request, self.template_name, ctx)

        except zipfile.BadZipFile:
            messages.error(request, 'The uploaded file is not a valid ZIP archive.')
            return redirect('backup:backup')
        except Exception as exc:
            messages.error(request, f'Could not read backup file: {exc}')
            return redirect('backup:backup')

    # ── restore: from local stored file ──────────────────────────

    def _handle_restore_local(self, request):
        filename = request.POST.get('filename', '').strip()
        if not filename:
            messages.error(request, 'Please specify a local backup file to restore.')
            return redirect('backup:backup')

        active_dir = get_configured_backup_dir()
        safe_name = Path(filename).name
        target_file = active_dir / safe_name

        if not target_file.exists() or not target_file.is_file():
            messages.error(request, f"File '{safe_name}' not found in '{active_dir}'.")
            return redirect('backup:backup')

        try:
            with zipfile.ZipFile(target_file, 'r') as zf:
                names = zf.namelist()
                has_sqlite = 'db.sqlite3' in names
                has_json   = 'data.json' in names
                has_pgdump = 'db.dump' in names

                if is_sqlite() and not has_sqlite:
                    messages.error(request, 'This backup does not contain a db.sqlite3 file.')
                    return redirect('backup:backup')

                if not is_sqlite() and not has_json and not has_pgdump:
                    messages.error(request, 'This backup does not contain data.json or db.dump.')
                    return redirect('backup:backup')

            # Copy to temp file for restore staging
            tmp_fd, tmp_path = tempfile.mkstemp(suffix='.zip', prefix='fwtbm_restore_')
            with os.fdopen(tmp_fd, 'wb') as f_out:
                with open(target_file, 'rb') as f_in:
                    shutil.copyfileobj(f_in, f_out)

            request.session['pending_restore_path'] = tmp_path
            request.session['pending_restore_name'] = safe_name

            file_count = len(names)
            ctx = self._context()
            ctx.update({
                'confirm_restore': True,
                'restore_filename': safe_name,
                'restore_file_count': file_count,
            })
            return render(request, self.template_name, ctx)

        except Exception as exc:
            messages.error(request, f'Could not prepare local restore: {exc}')
            return redirect('backup:backup')

    # ── restore: step 2 — confirmed, apply ───────────────────────

    def _handle_restore_confirm(self, request):
        tmp_path = request.session.pop('pending_restore_path', None)
        request.session.pop('pending_restore_name', None)

        if not tmp_path or not os.path.exists(tmp_path):
            messages.error(request, 'Session expired or temp file missing. Please initiate the restore again.')
            return redirect('backup:backup')

        try:
            with open(tmp_path, 'rb') as f:
                data = f.read()
        except Exception as exc:
            messages.error(request, f'Could not read temp file: {exc}')
            return redirect('backup:backup')
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        # 1. Snapshot active admin accounts
        from django.contrib.auth.models import User
        from accounts.models import UserProfile

        admin_snapshots = []
        try:
            for u in User.objects.filter(is_active=True):
                prof = getattr(u, 'profile', None)
                role = prof.role if prof else None
                if u.is_superuser or role == 'admin' or (request.user.is_authenticated and u.pk == request.user.pk):
                    admin_snapshots.append({
                        'username': u.username,
                        'password': u.password,
                        'email': u.email or '',
                        'first_name': u.first_name or '',
                        'last_name': u.last_name or '',
                        'is_superuser': True,
                        'is_staff': True,
                        'is_active': True,
                        'is_current_user': (request.user.is_authenticated and u.pk == request.user.pk),
                    })
        except Exception:
            pass

        # Auto-save current DB before overwriting
        saved_path = _auto_save_current_db('pre_restore')

        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if is_sqlite():
                    db_p = sqlite_path()
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite3') as tmp:
                        tmp.write(zf.read('db.sqlite3'))
                        new_tmp_path = tmp.name
                    shutil.move(new_tmp_path, db_p)
                else:
                    if 'db.dump' in zf.namelist():
                        self._pg_restore(zf.read('db.dump'))
                    elif 'data.json' in zf.namelist():
                        self._loaddata_json(zf.read('data.json'))

                # Restore media files
                m_root = media_root()
                for name in zf.namelist():
                    if name.startswith('media/') and not name.endswith('/'):
                        dest = m_root / Path(name).relative_to('media')
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(zf.read(name))

            # Close all DB connections
            from django.db import connections
            for conn in connections.all():
                try:
                    conn.close()
                except Exception:
                    pass

            # Automatically run migrations & full feature reconciliation pipeline on restored database
            try:
                from utils.reconciler import reconcile_all
                reconcile_report = reconcile_all(caller='backup_restore')
            except Exception as e:
                pass

            # 2. Re-apply / preserve admin accounts
            active_login_user = None
            preserved_usernames = []

            for adm in admin_snapshots:
                try:
                    target_user = User.objects.filter(username=adm['username']).first()
                    if target_user:
                        target_user.password = adm['password']
                        target_user.email = adm['email']
                        target_user.first_name = adm['first_name']
                        target_user.last_name = adm['last_name']
                        target_user.is_superuser = True
                        target_user.is_staff = True
                        target_user.is_active = True
                        target_user.save()
                    else:
                        target_user = User.objects.create(
                            username=adm['username'],
                            password=adm['password'],
                            email=adm['email'],
                            first_name=adm['first_name'],
                            last_name=adm['last_name'],
                            is_superuser=True,
                            is_staff=True,
                            is_active=True,
                        )

                    prof, _ = UserProfile.objects.get_or_create(user=target_user)
                    prof.role = 'admin'
                    prof.save()

                    preserved_usernames.append(target_user.username)
                    if adm.get('is_current_user'):
                        active_login_user = target_user
                except Exception:
                    pass

            if not active_login_user and preserved_usernames:
                active_login_user = User.objects.filter(username=preserved_usernames[0]).first()
            if not active_login_user:
                active_login_user = User.objects.filter(is_superuser=True, is_active=True).first()

            # Flush the stale in-memory session (its key does not exist in the newly restored database).
            # This is critical: otherwise SessionMiddleware attempts to update a non-existent session
            # row in the new database, raising SessionInterrupted.
            try:
                request.session.flush()
            except Exception:
                try:
                    request.session.clear()
                    request.session._session_key = None
                    request.session.modified = False
                except Exception:
                    pass

            if active_login_user:
                from django.contrib.auth import login as auth_login
                auth_login(request, active_login_user, backend='django.contrib.auth.backends.ModelBackend')
                try:
                    request.session.save()
                except Exception:
                    pass

            params = {
                'restored': '1',
                'saved_to': str(saved_path) if saved_path else '',
            }
            if active_login_user:
                params['preserved_admin'] = active_login_user.username
            return redirect(f"/backup/?{urlencode(params)}")

        except Exception as exc:
            try:
                request.session.flush()
            except Exception:
                try:
                    request.session.clear()
                    request.session._session_key = None
                    request.session.modified = False
                except Exception:
                    pass
            params = urlencode({'error': str(exc)})
            return redirect(f"/backup/?{params}")

    def _pg_restore(self, dump_bytes: bytes):
        db = db_conf()
        env = os.environ.copy()
        env['PGPASSWORD'] = db.get('PASSWORD', '')
        with tempfile.NamedTemporaryFile(delete=False, suffix='.dump') as f:
            f.write(dump_bytes)
            tmp = f.name
        try:
            subprocess.run([
                'pg_restore', '--clean', '--if-exists',
                '-h', db.get('HOST', 'localhost'),
                '-p', str(db.get('PORT', 5432)),
                '-U', db.get('USER', 'postgres'),
                '-d', db.get('NAME', ''),
                tmp,
            ], env=env, check=True, timeout=120)
        finally:
            os.unlink(tmp)

    def _loaddata_json(self, json_bytes: bytes):
        from django.core.management import call_command
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='wb') as f:
            f.write(json_bytes)
            tmp = f.name
        try:
            call_command('loaddata', tmp, verbosity=0)
        finally:
            os.unlink(tmp)

    # ── shared context ────────────────────────────────────────────

    def _context(self):
        sqlite_check = is_sqlite()
        db_display = 'SQLite' if sqlite_check else 'PostgreSQL'

        db_size = None
        if sqlite_check:
            p = sqlite_path()
            if p.exists():
                db_size = round(p.stat().st_size / (1024 * 1024), 2)

        media_size = None
        m_root = media_root()
        if m_root.exists():
            total = sum(f.stat().st_size for f in m_root.rglob('*') if f.is_file())
            media_size = round(total / (1024 * 1024), 2)

        setting = BackupSetting.get_settings()
        active_dir = get_configured_backup_dir(setting)
        default_auto_dir = get_system_default_backup_dir('automatic')
        default_sched_dir = get_system_default_backup_dir('scheduled')

        stored_backups = list_local_backups(active_dir)
        total_backups_count = len(stored_backups)
        total_backups_size_mb = round(sum(b['size_mb'] for b in stored_backups), 2)

        recent_logs = BackupLog.objects.all()[:10]

        # Calculate next backup estimate
        next_backup_str = None
        if setting.mode != 'manual':
            interval_hours = 24 if setting.mode == 'automatic' else setting.schedule_interval_hours
            if setting.last_backup_at:
                next_time = setting.last_backup_at + datetime.timedelta(hours=interval_hours)
                now = timezone.now()
                if next_time > now:
                    diff = next_time - now
                    hours = int(diff.total_seconds() // 3600)
                    mins = int((diff.total_seconds() % 3600) // 60)
                    next_backup_str = f"in {hours}h {mins}m ({timezone.localtime(next_time).strftime('%d %b %H:%M')})"
                else:
                    next_backup_str = "Pending next cycle / Due now"
            else:
                next_backup_str = "Scheduled immediately on next cycle"

        return {
            'db_engine': db_display,
            'db_size_mb': db_size,
            'media_size_mb': media_size,
            'setting': setting,
            'active_backup_dir': str(active_dir),
            'default_auto_dir': str(default_auto_dir),
            'default_sched_dir': str(default_sched_dir),
            'stored_backups': stored_backups,
            'total_backups_count': total_backups_count,
            'total_backups_size_mb': total_backups_size_mb,
            'recent_logs': recent_logs,
            'next_backup_str': next_backup_str,
        }


class DownloadLocalBackupView(AdminRequiredMixin, View):
    """Streams a stored backup file from the local backup directory."""
    def get(self, request, filename):
        active_dir = get_configured_backup_dir()
        safe_name = Path(filename).name
        target_file = active_dir / safe_name

        if not target_file.exists() or not target_file.is_file():
            raise Http404("Backup file not found.")

        try:
            with open(target_file, 'rb') as f:
                data = f.read()
            response = HttpResponse(data, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{safe_name}"'
            return response
        except Exception as exc:
            messages.error(request, f"Error downloading backup file: {exc}")
            return redirect('backup:backup')


class ValidateDirectoryAPIView(AdminRequiredMixin, View):
    """AJAX endpoint to test if a given directory path is valid and writable."""
    def post(self, request):
        path_str = request.POST.get('path', '').strip()
        valid, msg, norm_path = validate_backup_directory(path_str)
        return JsonResponse({
            'valid': valid,
            'message': msg,
            'normalized_path': norm_path,
        })
