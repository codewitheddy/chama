"""
JSON API views for the Finance Wise TBM Auto-Update UI.
========================================================
Exposes endpoints for:
1. Checking updates manually or automatically.
2. Triggering background streaming downloads.
3. Polling real-time download and verification progress.
4. Launching the verified installation and database backup handover.
5. Managing user preferences (Skip Version, Remind Me Later, Channel).
6. Central server client compatibility verification.
"""

import json
import os
import sys
import threading
import time
from dataclasses import asdict
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .compatibility import check_client_compatibility, check_pending_transactions_safety
from .services import UpdateService


def _get_service() -> UpdateService:
    return UpdateService()


@require_GET
def check_updates_api(request: HttpRequest) -> JsonResponse:
    """Check for latest published release."""
    force = request.GET.get("force", "").lower() in ("1", "true", "yes")
    channel = request.GET.get("channel", "").strip() or None
    service = _get_service()
    data = service.check_for_updates(channel=channel, force=force)
    return JsonResponse(data)


@require_POST
def start_download_api(request: HttpRequest) -> JsonResponse:
    """Trigger background download."""
    service = _get_service()
    try:
        service.start_download()
        return JsonResponse({"status": "DOWNLOADING", "message": "Download initiated in background."})
    except Exception as e:
        return JsonResponse({"status": "ERROR", "error": str(e)}, status=400)


@require_GET
def download_progress_api(request: HttpRequest) -> JsonResponse:
    """Return current state machine status and download progress."""
    service = _get_service()
    data = asdict(service.status)
    return JsonResponse(data)


@require_POST
def install_update_api(request: HttpRequest) -> JsonResponse:
    """
    Take safety backup and launch separate bootstrapper.
    Coordinates application shutdown.
    """
    service = _get_service()
    res = service.prepare_and_launch_update()
    if res.get("success"):
        # Schedule application process exit after 2.5 seconds to allow JSON response to complete
        def _deferred_exit():
            time.sleep(2.0)
            os._exit(0)
        t = threading.Thread(target=_deferred_exit, daemon=True)
        t.start()
        return JsonResponse({
            "status": "INSTALLING",
            "message": "Update prepared. Application will close and restart shortly.",
            "backup_path": service.status.backup_path,
        })
    else:
        return JsonResponse({"status": "ERROR", "error": res.get("error", "Failed to launch installer")}, status=500)


@require_POST
def skip_version_api(request: HttpRequest) -> JsonResponse:
    """Mark the current latest version as skipped."""
    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
        version = body.get("version") or request.POST.get("version", "")
    except Exception:
        version = request.POST.get("version", "")

    service = _get_service()
    target_version = version or service.status.latest_version
    if target_version:
        service.set_skipped_version(target_version)
        service.status.is_skipped = True
        return JsonResponse({"status": "OK", "skipped_version": target_version})
    return JsonResponse({"error": "No version specified"}, status=400)


@require_POST
def remind_later_api(request: HttpRequest) -> JsonResponse:
    """Postpone update notification (default 24 hours)."""
    try:
        body = json.loads(request.body.decode("utf-8")) if request.body else {}
        hours = int(body.get("hours", 24))
    except Exception:
        hours = int(request.POST.get("hours", 24))

    service = _get_service()
    service.set_remind_later(hours=hours)
    return JsonResponse({"status": "OK", "postponed_hours": hours})


@require_GET
def client_compatibility_api(request: HttpRequest) -> JsonResponse:
    """
    API endpoint for central servers to validate connecting desktop client versions.
    Example: GET /api/client-compatibility/?client_version=1.1.0
    """
    client_version = request.GET.get("client_version", "").strip()
    result = check_client_compatibility(client_version)
    status_code = 200 if result.get("compatible") else 426  # 426 Upgrade Required
    return JsonResponse(result, status=status_code)


@require_GET
def transaction_safety_api(request: HttpRequest) -> JsonResponse:
    """Verify pending transactions before allowing update."""
    data = check_pending_transactions_safety()
    return JsonResponse(data)
