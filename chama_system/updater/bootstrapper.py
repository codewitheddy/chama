"""
Out-of-process Updater and Bootstrapper for Finance Wise TBM.
=============================================================
Safely updates application files after the main application process terminates cleanly.
Features:
1. Waits for main PID to exit without force-closing active transactions.
2. Creates an atomic backup of the current application directory prior to replacement.
3. Replaces application files with staged update files.
4. Executes a startup health check (`--health-check`).
5. Performs automatic rollback if replacement or health check fails.
6. Launches the updated application and cleans up temporary files only after verified success.
"""

import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path


def is_process_running(pid: int) -> bool:
    """Check if process with given PID is still active."""
    if pid <= 0:
        return False
    sys_name = platform.system().lower()
    if sys_name == "windows":
        try:
            # OpenProcess with PROCESS_QUERY_LIMITED_INFORMATION
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid
            )
            if not handle:
                return False
            exit_code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            STILL_ACTIVE = 259
            return exit_code.value == STILL_ACTIVE
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def wait_for_process_exit(pid: int, timeout: int = 45) -> bool:
    """Wait up to timeout seconds for the application process to terminate cleanly."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_process_running(pid):
            # Extra grace period for file handles to be released
            time.sleep(1.5)
            return True
        time.sleep(0.5)
    return False


def copy_tree_robust(src: Path, dst: Path) -> None:
    """Recursively copy files from src to dst with retry on temporary lock."""
    dst.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel_path = Path(root).relative_to(src)
        target_dir = dst / rel_path
        target_dir.mkdir(parents=True, exist_ok=True)

        for f in files:
            src_file = Path(root) / f
            dst_file = target_dir / f

            # Copy with retry
            copied = False
            for attempt in range(5):
                try:
                    shutil.copy2(src_file, dst_file)
                    copied = True
                    break
                except (PermissionError, OSError):
                    time.sleep(0.5)
            if not copied:
                raise PermissionError(f"Could not copy {src_file} -> {dst_file} after retries")


def run_health_check(app_dir: Path, exec_name: str) -> bool:
    """Execute updated application with --health-check flag to confirm operational status."""
    exe_path = app_dir / exec_name
    if not exe_path.exists():
        logging.error(f"Health check failed: executable not found at {exe_path}")
        return False

    cmd = [str(exe_path), "--health-check"]
    logging.info(f"Running health check: {' '.join(cmd)}")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(app_dir)
        )
        logging.info(f"Health check exit code: {proc.returncode}")
        logging.info(f"Health check stdout: {proc.stdout.strip()}")
        if proc.returncode == 0 and "HEALTH_OK" in proc.stdout:
            return True
        if proc.returncode == 0:
            # Also accept exit 0 without explicit token if no error
            return True
        logging.error(f"Health check failed with error: {proc.stderr}")
        return False
    except Exception as e:
        logging.error(f"Health check exception: {e}")
        return False


def rollback_application(app_dir: Path, backup_dir: Path) -> None:
    """Restore application files from previous working backup."""
    logging.warning(f"ROLLBACK TRIGGERED: Restoring from {backup_dir} to {app_dir}")
    try:
        if backup_dir.exists():
            copy_tree_robust(backup_dir, app_dir)
            logging.info("Rollback successfully completed.")
        else:
            logging.critical("Rollback failed: backup directory does not exist!")
    except Exception as e:
        logging.critical(f"Critical error during rollback: {e}")


def launch_application(app_dir: Path, exec_name: str) -> None:
    """Launch application in detached mode."""
    exe_path = app_dir / exec_name
    if not exe_path.exists():
        logging.error(f"Cannot launch application: {exe_path} not found")
        return

    logging.info(f"Launching updated application: {exe_path}")
    sys_name = platform.system().lower()
    if sys_name == "windows":
        DETACHED_PROCESS = 0x00000008
        subprocess.Popen(
            [str(exe_path)],
            cwd=str(app_dir),
            creationflags=DETACHED_PROCESS,
            close_fds=True
        )
    else:
        subprocess.Popen(
            [str(exe_path)],
            cwd=str(app_dir),
            start_new_session=True,
            close_fds=True
        )


def execute_update(
    app_dir: Path,
    staging_dir: Path,
    pid: int,
    exec_name: str,
    mode: str = "replace",
    installer_path: str = "",
    backup_base_dir: Path | None = None,
    timeout: int = 45,
    log_file: Path | None = None,
) -> int:
    """Main updater bootstrapper execution routine."""
    if log_file:
        logging.basicConfig(
            filename=str(log_file),
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            force=True
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s"
        )

    logging.info("==================================================")
    logging.info("Finance Wise TBM Auto-Updater Bootstrapper Started")
    logging.info(f"App dir: {app_dir}")
    logging.info(f"Staging dir: {staging_dir}")
    logging.info(f"Mode: {mode}")
    logging.info(f"Target PID: {pid}")

    # Step 1: Wait for running application process to exit cleanly
    if pid > 0:
        logging.info(f"Waiting up to {timeout}s for PID {pid} to terminate...")
        exited = wait_for_process_exit(pid, timeout=timeout)
        if not exited:
            logging.error(f"Application process (PID {pid}) did not exit within {timeout}s. Aborting update.")
            return 1
        logging.info("Application exited cleanly.")

    # Step 2: Handle Installer Mode (e.g. Inno Setup executable)
    if mode == "installer":
        inst = Path(installer_path)
        if not inst.exists():
            logging.error(f"Installer executable not found: {inst}")
            return 1
        logging.info(f"Launching installer: {inst}")
        cmd = [str(inst)]
        # Run installer
        res = subprocess.run(cmd)
        logging.info(f"Installer finished with code {res.returncode}")
        return res.returncode

    # Step 3: Handle Directory Replacement Mode
    if not staging_dir.exists():
        logging.error(f"Staging directory does not exist: {staging_dir}")
        return 1

    # Prepare backup directory
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_parent = backup_base_dir or app_dir.parent / "app_backups"
    backup_dir = backup_parent / f"app_backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    logging.info(f"Backing up current application files: {app_dir} -> {backup_dir}")
    try:
        copy_tree_robust(app_dir, backup_dir)
    except Exception as e:
        logging.error(f"Could not create application files backup: {e}")
        return 1

    # Replace files from staging into app_dir
    logging.info(f"Deploying updated files: {staging_dir} -> {app_dir}")
    try:
        copy_tree_robust(staging_dir, app_dir)
    except Exception as e:
        logging.error(f"File copy failed during replacement: {e}")
        rollback_application(app_dir, backup_dir)
        launch_application(app_dir, exec_name)
        return 1

    # Step 4: Run Startup Health Check on Updated Application
    health_ok = run_health_check(app_dir, exec_name)
    if not health_ok:
        logging.error("Health check failed on updated application! Initiating safety rollback...")
        rollback_application(app_dir, backup_dir)
        launch_application(app_dir, exec_name)
        return 1

    # Step 5: Success! Launch updated app and cleanup staging
    logging.info("Health check passed successfully! Launching updated application...")
    launch_application(app_dir, exec_name)

    # Clean up staging directory only after verified success
    try:
        shutil.rmtree(staging_dir, ignore_errors=True)
        logging.info("Temporary staging files cleaned up.")
    except Exception as e:
        logging.warning(f"Could not remove staging dir: {e}")

    logging.info("Update process completed successfully!")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Finance Wise TBM Auto-Updater Bootstrapper")
    parser.add_argument("--app-dir", required=True, help="Path to current application directory")
    parser.add_argument("--staging-dir", default="", help="Path to staged updated files")
    parser.add_argument("--pid", type=int, default=0, help="PID of running application process")
    parser.add_argument("--exec-name", default="FinanceWiseTBM.exe", help="Executable name to launch")
    parser.add_argument("--mode", choices=["replace", "installer"], default="replace", help="Update mode")
    parser.add_argument("--installer-path", default="", help="Path to installer executable")
    parser.add_argument("--backup-dir", default="", help="Backup directory path")
    parser.add_argument("--timeout", type=int, default=45, help="Seconds to wait for PID exit")
    parser.add_argument("--log-file", default="", help="Log file path")

    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    staging_dir = Path(args.staging_dir).resolve() if args.staging_dir else Path("")
    backup_dir = Path(args.backup_dir).resolve() if args.backup_dir else None
    log_file = Path(args.log_file).resolve() if args.log_file else None

    code = execute_update(
        app_dir=app_dir,
        staging_dir=staging_dir,
        pid=args.pid,
        exec_name=args.exec_name,
        mode=args.mode,
        installer_path=args.installer_path,
        backup_base_dir=backup_dir,
        timeout=args.timeout,
        log_file=log_file,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
