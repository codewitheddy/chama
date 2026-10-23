"""
Backup & Restore Service Layer.

Provides high-level helpers for:
1. Manual, Automatic, and Scheduled backup archive creation.
2. System-determined and custom storage path management and validation.
3. Retention-based auto-pruning.
4. Local file discovery, download, and restore preparation.
5. Periodic background scheduler check.
"""

import io
import os
import shutil
import zipfile
import tempfile
import datetime
import subprocess
import time
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import BackupSetting, BackupLog


# ── Database & Media Helpers ──────────────────────────────────────────────────

def db_conf():
    """Return the default DB config dict."""
    return settings.DATABASES['default']


def is_sqlite():
    return 'sqlite3' in db_conf().get('ENGINE', '')


def sqlite_path() -> Path:
    """Absolute path to the SQLite file."""
    return Path(db_conf()['NAME'])


def media_root() -> Path:
    return Path(settings.MEDIA_ROOT)


def dumpdata_json() -> bytes:
    """Use Django's dumpdata to export all app data to JSON bytes."""
    from django.core.management import call_command
    buf = io.StringIO()
    call_command(
        'dumpdata',
        '--natural-foreign',
        '--natural-primary',
        '--indent', '2',
        exclude=[
            'contenttypes', 'auth.permission', 'admin.logentry',
            'sessions.session',
        ],
        stdout=buf,
        verbosity=0,
    )
    return buf.getvalue().encode('utf-8')


def pg_dump() -> bytes | None:
    """Try pg_dump; return bytes or None if unavailable."""
    db = db_conf()
    env = os.environ.copy()
    env['PGPASSWORD'] = db.get('PASSWORD', '')
    cmd = [
        'pg_dump',
        '-h', db.get('HOST', 'localhost'),
        '-p', str(db.get('PORT', 5432)),
        '-U', db.get('USER', 'postgres'),
        '-F', 'c',
        db.get('NAME', ''),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, env=env, timeout=120)
        if result.returncode == 0:
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def build_backup_zip(include_media: bool = True) -> io.BytesIO:
    """Build the backup ZIP in memory and return the BytesIO buffer."""
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        if is_sqlite():
            p = sqlite_path()
            if p.exists():
                zf.write(p, 'db.sqlite3')
        else:
            dump_b = pg_dump()
            if dump_b:
                zf.writestr('db.dump', dump_b)
            else:
                zf.writestr('data.json', dumpdata_json())

        # Include JSON export for portability
        try:
            zf.writestr('data.json', dumpdata_json())
        except Exception:
            pass

        # Media files
        if include_media:
            m_root = media_root()
            if m_root.exists():
                for file_path in m_root.rglob('*'):
                    if file_path.is_file():
                        arcname = Path('media') / file_path.relative_to(m_root)
                        zf.write(file_path, arcname)

        # Manifest
        manifest = (
            f"Finance Wise TBM — Data Backup\n"
            f"Created : {timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Engine  : {db_conf().get('ENGINE', 'unknown')}\n"
            f"Media Included: {'Yes' if include_media else 'No'}\n"
            f"Version : 2\n"
        )
        zf.writestr('MANIFEST.txt', manifest)

    buf.seek(0)
    return buf


# ── Directory Management ──────────────────────────────────────────────────────

def get_system_default_backup_dir(mode: str = 'automatic') -> Path:
    """
    Returns the standard system-determined backup directory.
    Default: %USERPROFILE%/Documents/FinanceWiseTBM_backups/<mode>/
    """
    base = Path(os.environ.get('USERPROFILE', Path.home())) / 'Documents' / 'FinanceWiseTBM_backups'
    if mode in ['automatic', 'scheduled', 'manual']:
        target = base / mode
    else:
        target = base / 'general'
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_configured_backup_dir(setting: BackupSetting | None = None) -> Path:
    """
    Determines the active destination path based on setting configuration.
    """
    if setting is None:
        setting = BackupSetting.get_settings()

    if setting.mode == 'scheduled' and setting.custom_location.strip():
        custom_path = Path(setting.custom_location.strip())
        try:
            custom_path.mkdir(parents=True, exist_ok=True)
            return custom_path
        except Exception:
            # Fallback if custom path is invalid/inaccessible
            return get_system_default_backup_dir('scheduled')
    elif setting.mode == 'automatic':
        return get_system_default_backup_dir('automatic')
    else:
        return get_system_default_backup_dir('manual')


def validate_backup_directory(path_str: str) -> tuple[bool, str, str]:
    """
    Validates if a directory path is valid, can be created, and is writable.
    Returns: (is_valid, message, normalized_path_str)
    """
    if not path_str or not path_str.strip():
        return False, "Directory path cannot be empty.", ""

    try:
        p = Path(path_str.strip()).resolve()
        p.mkdir(parents=True, exist_ok=True)

        # Test write permission by creating and removing a temp file
        test_file = p / f".fwtbm_write_test_{int(time.time())}.tmp"
        test_file.write_text("write_test", encoding="utf-8")
        test_file.unlink()

        return True, "Location is valid and writable.", str(p)
    except PermissionError:
        return False, f"Permission denied: cannot write to '{path_str}'.", ""
    except Exception as exc:
        return False, f"Invalid directory path: {exc}", ""


# ── Backup Creation & Retention ───────────────────────────────────────────────

def prune_old_backups(directory: Path, retention_limit: int) -> int:
    """
    Deletes oldest backup files in the directory if file count exceeds retention_limit.
    Returns number of pruned files.
    """
    if retention_limit <= 0 or not directory.exists():
        return 0

    backup_files = []
    for f in directory.glob('*.zip'):
        if f.is_file() and f.name.startswith('backup_'):
            try:
                backup_files.append((f.stat().st_mtime, f))
            except Exception:
                pass

    backup_files.sort(key=lambda x: x[0], reverse=True)  # Newest first

    pruned = 0
    if len(backup_files) > retention_limit:
        excess = backup_files[retention_limit:]
        for _, file_to_delete in excess:
            try:
                file_to_delete.unlink()
                pruned += 1
            except Exception:
                pass
    return pruned


def create_backup_file(
    trigger: str = 'manual',
    custom_dir: Path | None = None,
    include_media: bool = True
) -> tuple[bool, str, Path | None]:
    """
    Creates a backup zip file and saves it into the target directory.
    Updates BackupSetting and writes an entry to BackupLog.
    """
    start_time = time.time()
    setting = BackupSetting.get_settings()
    dest_dir = custom_dir if custom_dir else get_configured_backup_dir(setting)

    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        error_msg = f"Failed to access destination directory '{dest_dir}': {exc}"
        BackupLog.objects.create(
            trigger_type=trigger,
            status='failed',
            file_name='',
            file_path=str(dest_dir),
            error_message=error_msg,
            duration_seconds=round(time.time() - start_time, 2)
        )
        return False, error_msg, None

    now = timezone.localtime(timezone.now())
    prefix = {
        'automatic': 'backup_auto',
        'scheduled': 'backup_sched',
        'manual': 'backup_manual',
        'pre_restore': 'backup_safety',
    }.get(trigger, 'backup')

    filename = f"{prefix}_{now.strftime('%Y%m%d_%H%M%S')}.zip"
    dest_path = dest_dir / filename

    try:
        # Build archive buffer
        buf = build_backup_zip(include_media=include_media)
        data = buf.getvalue()
        file_size = len(data)

        # Write to temporary file in same folder first, then atomically replace
        tmp_fd, tmp_file_path = tempfile.mkstemp(suffix='.tmp', prefix='fwtbm_bkp_', dir=str(dest_dir))
        try:
            with os.fdopen(tmp_fd, 'wb') as f:
                f.write(data)
            shutil.move(tmp_file_path, dest_path)
        except Exception:
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
            raise

        # Auto-prune old backups in the directory
        retention = setting.retention_count
        pruned_count = prune_old_backups(dest_dir, retention)

        duration = round(time.time() - start_time, 2)

        # Update setting record
        setting.last_backup_at = timezone.now()
        setting.last_backup_status = 'success'
        setting.last_backup_file = filename
        setting.last_backup_trigger = trigger
        setting.save()

        # Log entry
        BackupLog.objects.create(
            timestamp=timezone.now(),
            trigger_type=trigger,
            status='success',
            file_name=filename,
            file_path=str(dest_path),
            file_size_bytes=file_size,
            duration_seconds=duration,
        )

        msg = f"Backup '{filename}' ({round(file_size / (1024 * 1024), 2)} MB) created successfully in {dest_dir}."
        if pruned_count > 0:
            msg += f" ({pruned_count} old backup file{'s' if pruned_count > 1 else ''} pruned based on retention policy)."

        return True, msg, dest_path

    except Exception as exc:
        duration = round(time.time() - start_time, 2)
        error_msg = f"Backup failed: {exc}"
        setting.last_backup_status = 'failed'
        setting.save()

        BackupLog.objects.create(
            timestamp=timezone.now(),
            trigger_type=trigger,
            status='failed',
            file_name=filename,
            file_path=str(dest_path),
            error_message=error_msg,
            duration_seconds=duration,
        )
        return False, error_msg, None


# ── File Discovery & Listing ──────────────────────────────────────────────────

def list_local_backups(directory: Path | None = None) -> list[dict]:
    """
    Scans the given (or active) backup directory and returns metadata for all backup archives.
    """
    if directory is None:
        directory = get_configured_backup_dir()

    if not directory.exists():
        return []

    backups = []
    for entry in directory.iterdir():
        if entry.is_file() and (entry.name.endswith('.zip') or entry.name.endswith('.sqlite3')):
            try:
                stat = entry.stat()
                mtime = datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.timezone.utc)
                local_mtime = timezone.localtime(mtime)

                # Determine trigger category from name
                name_lower = entry.name.lower()
                if 'auto' in name_lower:
                    trigger = 'automatic'
                    trigger_label = 'Automatic (System)'
                    badge_class = 'bg-primary-subtle text-primary border border-primary-subtle'
                elif 'sched' in name_lower:
                    trigger = 'scheduled'
                    trigger_label = 'Scheduled'
                    badge_class = 'bg-info-subtle text-info-emphasis border border-info-subtle'
                elif 'safety' in name_lower or 'pre_restore' in name_lower:
                    trigger = 'pre_restore'
                    trigger_label = 'Safety (Pre-Restore)'
                    badge_class = 'bg-warning-subtle text-warning-emphasis border border-warning-subtle'
                else:
                    trigger = 'manual'
                    trigger_label = 'Manual'
                    badge_class = 'bg-secondary-subtle text-secondary border border-secondary-subtle'

                backups.append({
                    'filename': entry.name,
                    'filepath': str(entry.resolve()),
                    'size_bytes': stat.st_size,
                    'size_mb': round(stat.st_size / (1024 * 1024), 2),
                    'modified_at': local_mtime,
                    'modified_str': local_mtime.strftime('%Y-%m-%d %H:%M:%S'),
                    'trigger': trigger,
                    'trigger_label': trigger_label,
                    'badge_class': badge_class,
                    'is_zip': entry.name.endswith('.zip'),
                })
            except Exception:
                continue

    # Sort newest first
    backups.sort(key=lambda x: x['modified_at'], reverse=True)
    return backups


def delete_local_backup(filename: str, directory: Path | None = None) -> tuple[bool, str]:
    """
    Safely deletes a specific backup file from the storage directory.
    """
    if directory is None:
        directory = get_configured_backup_dir()

    # Prevent path traversal
    safe_name = Path(filename).name
    target_file = directory / safe_name

    if not target_file.exists() or not target_file.is_file():
        return False, f"File '{safe_name}' does not exist in '{directory}'."

    try:
        target_file.unlink()
        return True, f"Backup file '{safe_name}' was deleted successfully."
    except Exception as exc:
        return False, f"Could not delete backup file: {exc}"


# ── Periodic Background Check ─────────────────────────────────────────────────

_last_check_time = 0


def check_and_run_background_backup() -> tuple[bool, str]:
    """
    Evaluates if an automatic or scheduled backup is due and runs it if required.
    Called periodically by background scheduler or lazily on admin requests.
    """
    global _last_check_time
    current_time = time.time()
    # Throttle checks to at most once per 60 seconds
    if current_time - _last_check_time < 60:
        return False, "Check throttled."

    _last_check_time = current_time

    try:
        setting = BackupSetting.get_settings()
    except Exception:
        return False, "Database not ready."

    if setting.mode == 'manual':
        return False, "Manual mode is active. No automated backup required."

    interval_hours = 24 if setting.mode == 'automatic' else setting.schedule_interval_hours
    if interval_hours <= 0:
        interval_hours = 24

    now = timezone.now()
    if setting.last_backup_at is not None:
        elapsed = (now - setting.last_backup_at).total_seconds() / 3600.0
        if elapsed < interval_hours:
            return False, f"Next backup due in {round(interval_hours - elapsed, 1)} hours."

    # Due! Execute backup
    success, msg, _ = create_backup_file(
        trigger=setting.mode,
        include_media=setting.include_media
    )
    return success, msg
