"""
Cross-platform data isolation and resilient SQLite backup management.
======================================================================
Ensures all user banking databases, media, keys, and session files reside
safely outside the replaceable application directory on Windows, Linux, and macOS.
Provides atomic SQLite backups via the native SQLite Online Backup API (handling WAL
and open connections), integrity validation, disk space checks, and migration logging.
"""

import json
import logging
import os
import platform
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


def get_user_data_dir() -> Path:
    """
    Return the persistent user data directory isolated from application files.
      - Windows: %APPDATA%/FinanceWiseTBM
      - Linux:   ~/.local/share/FinanceWiseTBM (or $XDG_DATA_HOME/FinanceWiseTBM)
      - macOS:   ~/Library/Application Support/FinanceWiseTBM
    """
    sys_name = platform.system().lower()
    home = Path.home()

    if sys_name == "windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        data_dir = base / "FinanceWiseTBM"
    elif sys_name == "darwin":
        data_dir = home / "Library" / "Application Support" / "FinanceWiseTBM"
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data) if xdg_data else home / ".local" / "share"
        data_dir = base / "FinanceWiseTBM"

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_active_db_path() -> Path:
    """Resolve the active SQLite database path."""
    custom_db = os.environ.get("DESKTOP_DB_PATH")
    if custom_db and Path(custom_db).is_file():
        return Path(custom_db)

    try:
        from django.conf import settings
        db_conf = settings.DATABASES.get("default", {})
        if "sqlite3" in db_conf.get("ENGINE", ""):
            p = Path(db_conf.get("NAME", ""))
            if p.is_file():
                return p
    except Exception:
        pass

    # Default to data dir db
    return get_user_data_dir() / "db.sqlite3"


def get_backups_dir() -> Path:
    """Directory for verified pre-update and disaster recovery database backups."""
    bdir = get_user_data_dir() / "backups" / "pre_update"
    bdir.mkdir(parents=True, exist_ok=True)
    return bdir


def get_staging_dir() -> Path:
    """Directory for staging downloaded update archives and binaries."""
    sdir = get_user_data_dir() / "updates" / "staging"
    sdir.mkdir(parents=True, exist_ok=True)
    return sdir


def check_disk_space(target_dir: Path, required_bytes: int) -> Tuple[bool, int, int]:
    """
    Check if target filesystem has sufficient free space.
    Returns (has_sufficient_space, free_bytes, required_bytes).
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(str(target_dir))
    return usage.free >= required_bytes, usage.free, required_bytes


# ── SQLite Online Backup API ─────────────────────────────────────────────────

def create_safe_sqlite_backup(
    source_db_path: Optional[Path] = None,
    backup_label: str = "pre_update",
    source_version: str = "1.1.0"
) -> Tuple[Path, dict[str, Any]]:
    """
    Create a consistent, non-torn SQLite backup using the SQLite Online Backup API.
    Handles active readers/writers and Write-Ahead Logging (WAL) checkpointing safely.
    Returns (backup_file_path, metadata_dict).
    """
    src_path = Path(source_db_path or get_active_db_path())
    if not src_path.is_file():
        raise FileNotFoundError(f"Source database does not exist: {src_path}")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_filename = f"db_backup_v{source_version}_{backup_label}_{timestamp}.sqlite3"
    dest_path = get_backups_dir() / backup_filename
    meta_path = dest_path.with_suffix(".json")

    logger.info(f"Initiating SQLite Online Backup: {src_path} -> {dest_path}")

    # Use read-only URI mode for source to prevent any unintended writes
    src_uri = f"file:{src_path.resolve().as_posix()}?mode=ro"
    src_conn = sqlite3.connect(src_uri, uri=True, timeout=60.0)
    dest_conn = sqlite3.connect(str(dest_path), timeout=60.0)

    try:
        # Step through backup in 100-page increments
        with dest_conn:
            src_conn.backup(dest_conn, pages=100)
    finally:
        dest_conn.close()
        src_conn.close()

    # Verify the backup immediately
    integrity_ok, table_count, err_msg = verify_sqlite_backup(dest_path)
    if not integrity_ok:
        if dest_path.exists():
            dest_path.unlink()
        raise RuntimeError(f"Database backup verification failed: {err_msg}")

    # Extract schema state from backup
    schema_state = extract_schema_metadata(dest_path)

    metadata = {
        "timestamp": timestamp,
        "source_db": str(src_path),
        "backup_db": str(dest_path),
        "source_version": source_version,
        "backup_label": backup_label,
        "file_size": dest_path.stat().st_size,
        "table_count": table_count,
        "schema_state": schema_state,
        "verified": True,
    }

    with open(meta_path, "w", encoding="utf-8") as mf:
        json.dump(metadata, mf, indent=2)

    logger.info(f"Verified backup successfully created: {dest_path} ({metadata['file_size']} bytes)")
    return dest_path, metadata


def verify_sqlite_backup(backup_path: Path) -> Tuple[bool, int, Optional[str]]:
    """
    Verify backup integrity using PRAGMA integrity_check and table introspection.
    Returns (is_valid, table_count, error_message).
    """
    if not backup_path.is_file() or backup_path.stat().st_size == 0:
        return False, 0, "Backup file is empty or missing"

    conn = None
    try:
        conn = sqlite3.connect(str(backup_path), timeout=30.0)
        cur = conn.cursor()

        # 1. Run PRAGMA integrity_check
        cur.execute("PRAGMA integrity_check;")
        row = cur.fetchone()
        if not row or row[0] != "ok":
            return False, 0, f"Integrity check failed: {row}"

        # 2. Count application tables
        cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        count = cur.fetchone()[0]
        if count == 0:
            return False, 0, "Database contains no tables"

        return True, count, None
    except Exception as e:
        return False, 0, str(e)
    finally:
        if conn:
            conn.close()


def extract_schema_metadata(db_path: Path) -> dict[str, Any]:
    """Inspect applied migrations from django_migrations table."""
    conn = None
    try:
        conn = sqlite3.connect(str(db_path), timeout=15.0)
        cur = conn.cursor()
        cur.execute("SELECT app, name, applied FROM django_migrations ORDER BY id DESC")
        rows = cur.fetchall()
        return {
            "total_applied_migrations": len(rows),
            "latest_migration": f"{rows[0][0]}.{rows[0][1]}" if rows else None,
            "recent_migrations": [{"app": r[0], "name": r[1], "applied": str(r[2])} for r in rows[:10]],
        }
    except Exception as e:
        return {"error": f"Could not read django_migrations: {e}"}
    finally:
        if conn:
            conn.close()


def restore_sqlite_backup(backup_path: Path, target_db_path: Optional[Path] = None) -> bool:
    """
    Restore a verified SQLite backup over the target database.
    Performs integrity check on backup before replacing target file.
    """
    target = Path(target_db_path or get_active_db_path())
    valid, _, err = verify_sqlite_backup(backup_path)
    if not valid:
        raise ValueError(f"Cannot restore invalid backup: {err}")

    # Use online backup API to copy restored data cleanly into target
    dest_conn = sqlite3.connect(str(target), timeout=60.0)
    src_conn = sqlite3.connect(f"file:{backup_path.resolve().as_posix()}?mode=ro", uri=True, timeout=60.0)
    try:
        with dest_conn:
            src_conn.backup(dest_conn, pages=100)
        logger.info(f"Database successfully restored from {backup_path} to {target}")
        return True
    finally:
        dest_conn.close()
        src_conn.close()
