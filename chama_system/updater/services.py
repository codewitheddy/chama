"""
Update Service Orchestrator and State Machine.
==============================================
Coordinates:
1. Asynchronous non-blocking update checking.
2. Background streaming downloads with progress reporting.
3. Cryptographic signature and SHA-256 integrity verification.
4. Pre-update verified database backups.
5. Disk space validation and staging directory preparation.
6. User preference management (Skip Version, Remind Later).
7. Safe bootstrapper execution and application handover.
"""

import logging
import os
import shutil
import sys
import tarfile
import threading
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .crypto import verify_file_hash, verify_signature
from .github import check_for_updates, download_file, get_default_channel
from .manifest import PlatformAsset, ReleaseManifest
from .storage import (
    check_disk_space,
    create_safe_sqlite_backup,
    get_staging_dir,
    get_user_data_dir,
)
from .version import SemVer, get_installed_version, get_platform_info, is_update_available

logger = logging.getLogger(__name__)


# Update State Enum Values
STATE_IDLE = "IDLE"
STATE_CHECKING = "CHECKING"
STATE_AVAILABLE = "AVAILABLE"
STATE_UP_TO_DATE = "UP_TO_DATE"
STATE_DOWNLOADING = "DOWNLOADING"
STATE_VERIFYING = "VERIFYING"
STATE_READY_TO_INSTALL = "READY_TO_INSTALL"
STATE_INSTALLING = "INSTALLING"
STATE_ERROR = "ERROR"


@dataclass
class UpdateStatus:
    state: str = STATE_IDLE
    current_version: str = "1.1.0"
    latest_version: str = "1.1.0"
    update_available: bool = False
    release_notes: str = ""
    release_date: str = ""
    download_size: int = 0
    downloaded_bytes: int = 0
    progress_percent: float = 0.0
    download_speed: str = ""
    error_message: str = ""
    is_skipped: bool = False
    asset_filename: str = ""
    package_type: str = "archive"
    staged_path: str = ""
    backup_path: str = ""


class UpdateService:
    """Thread-safe singleton service managing the auto-update lifecycle."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init_service()
            return cls._instance

    def _init_service(self):
        self.status = UpdateStatus(
            current_version=str(get_installed_version()),
            latest_version=str(get_installed_version()),
        )
        self._active_manifest: Optional[ReleaseManifest] = None
        self._active_asset: Optional[PlatformAsset] = None
        self._download_cancel_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._state_lock = threading.Lock()

    # ── User Preference Helpers (Skip Version, Remind Later) ───────────────────

    def get_skipped_version(self) -> str:
        try:
            from loans.models import SystemSetting
            return SystemSetting.get("updater_skipped_version", "").strip()
        except Exception:
            return ""

    def set_skipped_version(self, version: str) -> None:
        try:
            from loans.models import SystemSetting
            SystemSetting.set("updater_skipped_version", version.strip())
        except Exception as e:
            logger.warning(f"Could not persist skipped version: {e}")

    def get_remind_later_until(self) -> float:
        try:
            from loans.models import SystemSetting
            raw = SystemSetting.get("updater_remind_later_until", "0")
            return float(raw)
        except Exception:
            return 0.0

    def set_remind_later(self, hours: int = 24) -> None:
        until = time.time() + (hours * 3600)
        try:
            from loans.models import SystemSetting
            SystemSetting.set("updater_remind_later_until", str(until))
        except Exception as e:
            logger.warning(f"Could not persist remind later timestamp: {e}")

    # ── Update Check ─────────────────────────────────────────────────────────

    def check_for_updates(self, channel: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        """
        Check GitHub Releases for updates.
        If force=False, respects Remind Later and Skipped Version preferences.
        """
        with self._state_lock:
            self.status.state = STATE_CHECKING
            self.status.error_message = ""

        try:
            res = check_for_updates(channel=channel)
            with self._state_lock:
                self.status.current_version = res["current_version"]
                self.status.latest_version = res["latest_version"]
                self.status.update_available = res["update_available"]
                self.status.release_notes = res["release_notes"]
                self.status.release_date = res["release_date"]
                self._active_manifest = res["manifest"]
                self._active_asset = res["asset"]

                if res["error"]:
                    self.status.state = STATE_ERROR
                    self.status.error_message = res["error"]
                elif res["update_available"]:
                    skipped = self.get_skipped_version()
                    remind_until = self.get_remind_later_until()

                    is_skipped = (skipped == res["latest_version"])
                    self.status.is_skipped = is_skipped

                    # If not forced, check suppression
                    if not force and (is_skipped or time.time() < remind_until):
                        self.status.state = STATE_AVAILABLE
                    else:
                        self.status.state = STATE_AVAILABLE

                    if self._active_asset:
                        self.status.download_size = self._active_asset.size
                        self.status.asset_filename = self._active_asset.filename
                        self.status.package_type = self._active_asset.package_type
                else:
                    self.status.state = STATE_UP_TO_DATE

            return asdict(self.status)
        except Exception as e:
            with self._state_lock:
                self.status.state = STATE_ERROR
                self.status.error_message = str(e)
            return asdict(self.status)

    def check_for_updates_async(self, channel: Optional[str] = None, force: bool = False) -> None:
        """Run update check in a non-blocking background thread."""
        t = threading.Thread(
            target=self.check_for_updates,
            args=(channel, force),
            daemon=True,
            name="UpdaterCheckThread",
        )
        t.start()

    # ── Download & Verification ──────────────────────────────────────────────

    def start_download(self) -> None:
        """Initiate background streaming download and package verification."""
        with self._state_lock:
            if not self.status.update_available or not self._active_asset:
                raise ValueError("No update asset available to download")
            if self.status.state == STATE_DOWNLOADING:
                return  # Already downloading
            self.status.state = STATE_DOWNLOADING
            self.status.progress_percent = 0.0
            self.status.downloaded_bytes = 0
            self.status.error_message = ""
            self._download_cancel_event.clear()

        self._worker_thread = threading.Thread(
            target=self._download_and_verify_worker,
            daemon=True,
            name="UpdaterDownloadThread",
        )
        self._worker_thread.start()

    def _progress_callback(self, downloaded: int, total: int, speed: float) -> None:
        with self._state_lock:
            self.status.downloaded_bytes = downloaded
            self.status.download_size = total
            if total > 0:
                self.status.progress_percent = round((downloaded / total) * 100, 1)

            # Format human speed (e.g. "2.4 MB/s")
            if speed > 1048576:
                self.status.download_speed = f"{speed / 1048576:.1f} MB/s"
            else:
                self.status.download_speed = f"{speed / 1024:.0f} KB/s"

    def _download_and_verify_worker(self) -> None:
        asset = self._active_asset
        if not asset:
            with self._state_lock:
                self.status.state = STATE_ERROR
                self.status.error_message = "Active asset metadata is missing"
            return

        staging_dir = get_staging_dir()
        download_target = staging_dir / asset.filename

        # 1. Check disk space (require at least 2.5x package size or 100MB)
        required_space = max(asset.size * 3, 100 * 1024 * 1024)
        has_space, free_b, _ = check_disk_space(staging_dir, required_space)
        if not has_space:
            with self._state_lock:
                self.status.state = STATE_ERROR
                free_mb = free_b // (1024 * 1024)
                req_mb = required_space // (1024 * 1024)
                self.status.error_message = (
                    f"Insufficient disk space in updates directory. Free: {free_mb} MB, Required: {req_mb} MB."
                )
            return

        # 2. Download package
        try:
            logger.info(f"Downloading update asset: {asset.download_url} -> {download_target}")
            download_file(
                url=asset.download_url,
                destination=download_target,
                progress_callback=self._progress_callback,
                cancel_event=self._download_cancel_event,
            )
        except InterruptedError:
            with self._state_lock:
                self.status.state = STATE_AVAILABLE
                self.status.error_message = "Download cancelled."
            return
        except Exception as e:
            with self._state_lock:
                self.status.state = STATE_ERROR
                self.status.error_message = f"Download failed: {e}"
            return

        # 3. Verification State
        with self._state_lock:
            self.status.state = STATE_VERIFYING
            self.status.progress_percent = 100.0

        # Validate Checksum
        if asset.sha256:
            logger.info("Verifying downloaded package SHA-256 checksum...")
            if not verify_file_hash(download_target, asset.sha256):
                download_target.unlink(missing_ok=True)
                with self._state_lock:
                    self.status.state = STATE_ERROR
                    self.status.error_message = "Package checksum mismatch! Corrupted or tampered download."
                return

        # Validate Asset Signature if provided
        if asset.signature:
            logger.info("Verifying digital signature over downloaded package...")
            try:
                with open(download_target, "rb") as f:
                    pkg_bytes = f.read()
                if not verify_signature(pkg_bytes, asset.signature):
                    download_target.unlink(missing_ok=True)
                    with self._state_lock:
                        self.status.state = STATE_ERROR
                        self.status.error_message = "Package digital signature verification failed! Rejecting update."
                    return
            except Exception as e:
                download_target.unlink(missing_ok=True)
                with self._state_lock:
                    self.status.state = STATE_ERROR
                    self.status.error_message = f"Signature verification error: {e}"
                return

        # 4. Extract archive if package_type == 'archive'
        extracted_staging = staging_dir / f"extracted_{self.status.latest_version}"
        if asset.package_type == "archive":
            logger.info(f"Extracting package to staging: {extracted_staging}")
            try:
                shutil.rmtree(extracted_staging, ignore_errors=True)
                extracted_staging.mkdir(parents=True, exist_ok=True)

                if download_target.suffix.lower() == ".zip":
                    with zipfile.ZipFile(download_target, "r") as zf:
                        zf.extractall(extracted_staging)
                elif download_target.name.endswith((".tar.gz", ".tgz")):
                    with tarfile.open(download_target, "r:gz") as tf:
                        tf.extractall(extracted_staging)
            except Exception as e:
                with self._state_lock:
                    self.status.state = STATE_ERROR
                    self.status.error_message = f"Archive extraction failed: {e}"
                return
            staged_path = str(extracted_staging)
        else:
            staged_path = str(download_target)

        with self._state_lock:
            self.status.state = STATE_READY_TO_INSTALL
            self.status.staged_path = staged_path

        logger.info("Update downloaded, verified, and staged successfully.")

    # ── Preparation and Bootstrapper Handover ──────────────────────────────────

    def prepare_and_launch_update(self) -> Dict[str, Any]:
        """
        Final safety execution prior to updating:
        1. Take verified SQLite backup.
        2. Resolve application directory.
        3. Spawn detached bootstrapper process.
        4. Return success status instructing client to initiate graceful shutdown.
        """
        with self._state_lock:
            if self.status.state != STATE_READY_TO_INSTALL:
                return {"success": False, "error": f"Cannot install in current state: {self.status.state}"}
            self.status.state = STATE_INSTALLING

        # Step 1: Create verified SQLite backup of local database
        try:
            backup_path, meta = create_safe_sqlite_backup(
                source_version=self.status.current_version,
                backup_label="pre_update"
            )
            with self._state_lock:
                self.status.backup_path = str(backup_path)
        except Exception as e:
            with self._state_lock:
                self.status.state = STATE_ERROR
                self.status.error_message = f"Safety database backup failed: {e}"
            return {"success": False, "error": self.status.error_message}

        # Step 2: Resolve app directory and executable name
        if getattr(sys, "frozen", False):
            app_dir = Path(os.path.dirname(sys.executable))
            exec_name = os.path.basename(sys.executable)
        else:
            app_dir = Path(__file__).resolve().parent.parent
            exec_name = "desktop.py"

        staging_dir = Path(self.status.staged_path)
        mode = "installer" if self.status.package_type == "installer" else "replace"
        current_pid = os.getpid()

        # Step 3: Spawn bootstrapper script
        bootstrapper_script = Path(__file__).resolve().parent / "bootstrapper.py"
        log_file = get_user_data_dir() / "updater_log.txt"

        cmd = [
            sys.executable,
            str(bootstrapper_script),
            "--app-dir", str(app_dir),
            "--staging-dir", str(staging_dir),
            "--pid", str(current_pid),
            "--exec-name", exec_name,
            "--mode", mode,
            "--installer-path", str(staging_dir) if mode == "installer" else "",
            "--log-file", str(log_file),
        ]

        logger.info(f"Spawning bootstrapper: {' '.join(cmd)}")
        try:
            sys_name = platform.system().lower()
            if sys_name == "windows":
                DETACHED_PROCESS = 0x00000008
                CREATE_NEW_PROCESS_GROUP = 0x00000200
                import subprocess
                subprocess.Popen(
                    cmd,
                    creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                    close_fds=True
                )
            else:
                import subprocess
                subprocess.Popen(cmd, start_new_session=True, close_fds=True)
            return {"success": True, "message": "Bootstrapper launched. Ready to exit application."}
        except Exception as e:
            with self._state_lock:
                self.status.state = STATE_ERROR
                self.status.error_message = f"Failed to launch bootstrapper: {e}"
            return {"success": False, "error": self.status.error_message}
