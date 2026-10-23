"""
Background backup scheduler daemon.
Periodically checks whether an automatic or scheduled backup is due.
"""

import threading
import time
import sys
import logging

logger = logging.getLogger(__name__)

_scheduler_thread = None
_stop_event = threading.Event()
_lock = threading.Lock()


def _scheduler_loop(interval_seconds: int = 180):
    """Loop that wakes up every `interval_seconds` and checks if backup is due."""
    # Delay initial check by 15 seconds after server boot to allow full startup
    time.sleep(15)
    while not _stop_event.is_set():
        try:
            from .services import check_and_run_background_backup
            ran, msg = check_and_run_background_backup()
            if ran:
                logger.info(f"[BackupScheduler] Background backup executed: {msg}")
        except Exception as exc:
            logger.warning(f"[BackupScheduler] Background backup check error: {exc}")

        # Sleep in small increments to respond quickly to shutdown events
        for _ in range(interval_seconds // 5):
            if _stop_event.is_set():
                break
            time.sleep(5)


def start_scheduler():
    """Start the background daemon thread if not already running."""
    global _scheduler_thread

    # Avoid running scheduler during management commands like test, makemigrations, migrate
    blocked_commands = ['migrate', 'makemigrations', 'test', 'collectstatic', 'shell']
    if any(cmd in sys.argv for cmd in blocked_commands):
        return

    with _lock:
        if _scheduler_thread is None or not _scheduler_thread.is_alive():
            _stop_event.clear()
            _scheduler_thread = threading.Thread(
                target=_scheduler_loop,
                name="FinanceWiseBackupScheduler",
                daemon=True
            )
            _scheduler_thread.start()
            logger.info("[BackupScheduler] Background backup daemon started.")


def stop_scheduler():
    """Stop the background scheduler thread."""
    global _scheduler_thread
    with _lock:
        if _scheduler_thread and _scheduler_thread.is_alive():
            _stop_event.set()
            _scheduler_thread = None
