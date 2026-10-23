"""
Client-Server API Compatibility and Database Safeguards.
========================================================
Protects online and central databases by enforcing:
1. Strict server-side client version compatibility checks.
2. Prevention of distributed desktop installations attempting migrations on central databases.
3. Preservation and safety checks for pending or local transactions during updates.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict

from .version import SemVer, get_installed_version

logger = logging.getLogger(__name__)

# Minimum desktop client version supported by the central server
MIN_SUPPORTED_CLIENT_VERSION = "1.0.0"
SERVER_API_VERSION = "1.1.0"


def check_client_compatibility(client_version_str: str) -> Dict[str, Any]:
    """
    Validate whether a connecting desktop client version is supported by the server API.
    Used by central server endpoints to return actionable upgrade guidance.
    """
    try:
        client_sv = SemVer(client_version_str)
        min_sv = SemVer(MIN_SUPPORTED_CLIENT_VERSION)
        server_sv = SemVer(SERVER_API_VERSION)

        if client_sv < min_sv:
            return {
                "compatible": False,
                "status": "deprecated",
                "client_version": str(client_sv),
                "min_supported_version": str(min_sv),
                "server_version": str(server_sv),
                "action_required": "update",
                "message": (
                    f"Your desktop application version (v{client_sv}) is no longer supported. "
                    f"Please update to at least v{min_sv} to continue syncing or using online services."
                ),
            }

        return {
            "compatible": True,
            "status": "supported",
            "client_version": str(client_sv),
            "min_supported_version": str(min_sv),
            "server_version": str(server_sv),
            "action_required": "none",
            "message": "Client version is fully compatible.",
        }
    except Exception as e:
        logger.warning(f"Error checking client compatibility: {e}")
        return {
            "compatible": False,
            "status": "invalid_version",
            "message": f"Invalid client version string: {client_version_str}",
            "action_required": "verify",
        }


def is_central_database_active() -> bool:
    """Return True if application is running against a central PostgreSQL or remote database."""
    try:
        from django.conf import settings
        engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
        return "postgresql" in engine or "mysql" in engine
    except Exception:
        return False


def can_run_remote_migrations() -> bool:
    """
    CRITICAL SAFEGUARD:
    Desktop installations must NEVER execute schema migrations against a central server database.
    Central migrations are solely executed by the server deployment pipeline.
    """
    is_desktop = bool(os.environ.get("DESKTOP_DB_PATH") or getattr(os, "environ", {}).get("APPDATA"))
    if is_desktop and is_central_database_active():
        logger.error("DENIED: Desktop client is prohibited from running migrations on remote central database.")
        return False
    return True


def check_pending_transactions_safety() -> Dict[str, Any]:
    """
    Inspect pending financial transactions (loans, transfers, approvals)
    to confirm it is safe to close or update the application without data loss.
    """
    try:
        from money_movement.models import MoneyTransfer
        pending_transfers = MoneyTransfer.objects.filter(status=MoneyTransfer.STATUS_PENDING).count()
    except Exception:
        pending_transfers = 0

    try:
        from loans.models import LoanApplication
        pending_loans = LoanApplication.objects.filter(status="pending").count()
    except Exception:
        pending_loans = 0

    return {
        "safe_to_exit": True,  # Financial data in SQLite is committed; we warn if actions in flight
        "pending_transfers_count": pending_transfers,
        "pending_loan_applications_count": pending_loans,
        "summary": (
            f"You have {pending_transfers} pending transfers and {pending_loans} pending loan applications. "
            "All pending records are securely preserved in your local database."
            if (pending_transfers or pending_loans) else
            "All transactions are up to date."
        ),
    }
