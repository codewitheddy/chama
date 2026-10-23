"""
GitHub Releases integration for Finance Wise TBM.
==================================================
Queries the GitHub REST API for published releases, filters by channel
(stable vs beta), handles rate limits, offline conditions, and fetches
release assets and cryptographic signatures.
"""

import json
import logging
import os
import socket
import ssl
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .crypto import verify_signature, get_trusted_public_key
from .manifest import ReleaseManifest, PlatformAsset
from .version import SemVer, get_installed_version, is_update_available

logger = logging.getLogger(__name__)


def get_repo_owner() -> str:
    """Resolve GitHub repository owner from environment, settings, or default."""
    if os.environ.get("GITHUB_REPO_OWNER"):
        return os.environ.get("GITHUB_REPO_OWNER").strip()
    try:
        from django.conf import settings
        return getattr(settings, "GITHUB_REPO_OWNER", "codewitheddy").strip()
    except Exception:
        return "codewitheddy"


def get_repo_name() -> str:
    """Resolve GitHub repository name from environment, settings, or default."""
    if os.environ.get("GITHUB_REPO_NAME"):
        return os.environ.get("GITHUB_REPO_NAME").strip()
    try:
        from django.conf import settings
        return getattr(settings, "GITHUB_REPO_NAME", "chama").strip()
    except Exception:
        return "chama"


def get_default_channel() -> str:
    """Resolve default release channel ('stable' or 'beta')."""
    if os.environ.get("UPDATE_CHANNEL"):
        return os.environ.get("UPDATE_CHANNEL").strip().lower()
    try:
        from django.conf import settings
        return getattr(settings, "UPDATE_CHANNEL", "stable").strip().lower()
    except Exception:
        return "stable"


def _build_request(url: str, auth_token: Optional[str] = None) -> Request:
    """Construct an authorized HTTP request with proper User-Agent and headers."""
    req = Request(url)
    req.add_header("User-Agent", f"FinanceWiseTBM-Updater/{get_installed_version()}")
    req.add_header("Accept", "application/vnd.github.v3+json")

    # Optional token for private repos (only if set via env or settings, never embedded)
    token = auth_token or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return req


def fetch_releases(
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    timeout: int = 15
) -> Tuple[str, list[dict[str, Any]], Optional[str]]:
    """
    Fetch releases list from GitHub API.
    Returns (status, releases_list, error_message).
    Status values: 'ok', 'offline', 'rate_limited', 'not_found', 'error'.
    """
    owner = owner or get_repo_owner()
    repo = repo or get_repo_name()
    url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=30"

    try:
        req = _build_request(url)
        context = ssl.create_default_context()
        with urlopen(req, timeout=timeout, context=context) as resp:
            data = resp.read().decode("utf-8")
            releases = json.loads(data)
            return "ok", releases, None
    except HTTPError as e:
        if e.code in (403, 429):
            logger.warning("GitHub API rate limit exceeded.")
            return "rate_limited", [], "GitHub API rate limit reached. Please check back later."
        elif e.code == 404:
            logger.warning(f"GitHub repository {owner}/{repo} or releases not found.")
            return "not_found", [], f"Repository {owner}/{repo} not found on GitHub."
        return "error", [], f"HTTP error {e.code}: {e.reason}"
    except (URLError, socket.gaierror, socket.timeout, TimeoutError) as e:
        logger.info(f"Network unreachable for update check: {e}")
        return "offline", [], "Internet or GitHub service unreachable. Application running normally in offline mode."
    except Exception as e:
        logger.exception(f"Unexpected error fetching GitHub releases: {e}")
        return "error", [], str(e)


def check_for_updates(
    channel: Optional[str] = None,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    timeout: int = 15
) -> dict[str, Any]:
    """
    High-level check for updates against GitHub Releases.
    Returns a structured dictionary with update information:
      - status: 'update_available' | 'up_to_date' | 'offline' | 'rate_limited' | 'error'
      - current_version: str
      - latest_version: str
      - release_notes: str
      - release_date: str
      - manifest: ReleaseManifest or None
      - asset: PlatformAsset or None
      - error: str or None
    """
    channel = (channel or get_default_channel()).lower()
    current_version = str(get_installed_version())

    status, releases, error_msg = fetch_releases(owner, repo, timeout=timeout)
    if status != "ok":
        return {
            "status": status,
            "current_version": current_version,
            "latest_version": current_version,
            "update_available": False,
            "release_notes": "",
            "release_date": "",
            "manifest": None,
            "asset": None,
            "error": error_msg,
        }

    # Filter releases by channel and draft status
    eligible_releases: list[dict[str, Any]] = []
    for rel in releases:
        if rel.get("draft", False):
            continue  # Always ignore drafts
        is_pre = rel.get("prerelease", False)
        if channel == "stable" and is_pre:
            continue  # Ignore prereleases in stable channel
        eligible_releases.append(rel)

    if not eligible_releases:
        return {
            "status": "up_to_date",
            "current_version": current_version,
            "latest_version": current_version,
            "update_available": False,
            "release_notes": "",
            "release_date": "",
            "manifest": None,
            "asset": None,
            "error": None,
        }

    # Find the release with the highest semantic version
    best_release = None
    best_semver = None
    for rel in eligible_releases:
        tag = rel.get("tag_name", "").lstrip("v")
        try:
            sv = SemVer(tag)
            if best_semver is None or sv > best_semver:
                best_semver = sv
                best_release = rel
        except Exception:
            continue

    if not best_release or not best_semver:
        return {
            "status": "up_to_date",
            "current_version": current_version,
            "latest_version": current_version,
            "update_available": False,
            "release_notes": "",
            "release_date": "",
            "manifest": None,
            "asset": None,
            "error": None,
        }

    latest_version_str = str(best_semver)
    has_update = is_update_available(current_version, latest_version_str)

    # Inspect assets for manifest.json and manifest.json.sig
    manifest, manifest_err = _resolve_manifest(best_release, latest_version_str, channel)
    asset = manifest.get_asset_for_current_platform() if manifest else None

    return {
        "status": "update_available" if has_update else "up_to_date",
        "current_version": current_version,
        "latest_version": latest_version_str,
        "update_available": has_update,
        "release_notes": best_release.get("body", "") or "",
        "release_date": best_release.get("published_at", "") or "",
        "manifest": manifest,
        "asset": asset,
        "error": manifest_err,
    }


def _resolve_manifest(
    release_dict: dict[str, Any],
    version_str: str,
    channel: str
) -> Tuple[Optional[ReleaseManifest], Optional[str]]:
    """Download and verify manifest.json, or synthesize one from release assets."""
    assets = release_dict.get("assets", [])
    manifest_asset = next((a for a in assets if a.get("name") == "manifest.json"), None)
    sig_asset = next((a for a in assets if a.get("name") in ("manifest.json.sig", "manifest.sig")), None)

    # 1. If explicit manifest.json asset exists
    if manifest_asset:
        try:
            req = _build_request(manifest_asset["browser_download_url"])
            context = ssl.create_default_context()
            with urlopen(req, timeout=15, context=context) as resp:
                manifest_bytes = resp.read()

            sig_hex = ""
            if sig_asset:
                req_sig = _build_request(sig_asset["browser_download_url"])
                with urlopen(req_sig, timeout=10, context=context) as sresp:
                    sig_hex = sresp.read().decode("utf-8").strip()

            # Cryptographic verification: verify signature against trusted public key
            if sig_hex:
                valid = verify_signature(manifest_bytes, sig_hex)
                if not valid:
                    return None, "Digital signature verification failed for release manifest! Possible tampering."

            manifest = ReleaseManifest.from_json(manifest_bytes.decode("utf-8"), raw_signature=sig_hex)
            return manifest, None
        except Exception as e:
            logger.warning(f"Could not load release manifest from asset: {e}")

    # 2. Synthesize manifest from GitHub release asset list
    syn_assets: dict[str, PlatformAsset] = {}
    for a in assets:
        name = a.get("name", "")
        url = a.get("browser_download_url", "")
        size = int(a.get("size", 0))

        # Detect platform from filename
        lower_name = name.lower()
        if "windows" in lower_name or lower_name.endswith(".exe") or "win" in lower_name:
            key = "windows-x86_64"
            pkg_type = "installer" if lower_name.endswith(".exe") else "archive"
        elif "linux" in lower_name:
            key = "linux-x86_64"
            pkg_type = "archive"
        elif "macos" in lower_name or "darwin" in lower_name:
            key = "macos-arm64" if "arm64" in lower_name or "m1" in lower_name else "macos-x86_64"
            pkg_type = "archive"
        else:
            continue

        if key not in syn_assets or pkg_type == "archive":
            syn_assets[key] = PlatformAsset(
                filename=name,
                download_url=url,
                sha256="",  # Will be verified if checksum asset exists or provided in release notes
                size=size,
                package_type=pkg_type,
            )

    synth_manifest = ReleaseManifest(
        version=version_str,
        release_date=release_dict.get("published_at", ""),
        min_updater_version="1.0.0",
        channel=channel,
        release_notes=release_dict.get("body", "") or "",
        assets=syn_assets,
    )
    return synth_manifest, None


def download_file(
    url: str,
    destination: Path,
    progress_callback: Optional[Callable[[int, int, float], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    chunk_size: int = 65536
) -> Path:
    """
    Stream download a file with progress tracking, atomic rename, and cancellation support.
    progress_callback receives: (bytes_downloaded, total_bytes, speed_bytes_per_sec).
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_file = destination.with_suffix(f"{destination.suffix}.part")

    req = _build_request(url)
    context = ssl.create_default_context()

    start_time = time.time()
    downloaded = 0

    with urlopen(req, timeout=30, context=context) as response:
        total_size = int(response.headers.get("Content-Length", 0))

        with open(temp_file, "wb") as out_f:
            while True:
                if cancel_event and cancel_event.is_set():
                    if temp_file.exists():
                        temp_file.unlink(missing_ok=True)
                    raise InterruptedError("Download was cancelled by user.")

                chunk = response.read(chunk_size)
                if not chunk:
                    break

                out_f.write(chunk)
                downloaded += len(chunk)

                if progress_callback:
                    elapsed = max(time.time() - start_time, 0.001)
                    speed = downloaded / elapsed
                    progress_callback(downloaded, total_size, speed)

    # Atomic move to final destination
    if destination.exists():
        destination.unlink()
    temp_file.rename(destination)
    return destination
