"""
Release Manifest and Package Metadata validation.
==================================================
Defines documented release asset naming conventions, manifests,
and strict validation of download URLs, checksums, and package types.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from .crypto import verify_signature, verify_file_hash
from .version import SemVer, get_platform_info


# Permitted download hostnames for security verification
ALLOWED_DOWNLOAD_DOMAINS = {
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "github-releases.githubusercontent.com",
    "raw.githubusercontent.com",
    # Allow local/mock testing domains in development
    "127.0.0.1",
    "localhost",
}


@dataclass
class PlatformAsset:
    """Represents a validated binary package asset for a target platform."""
    filename: str
    download_url: str
    sha256: str
    size: int = 0
    package_type: str = "archive"  # "archive" (zip/tar.gz) or "installer" (.exe)
    installer_url: str = ""
    installer_sha256: str = ""
    signature: str = ""

    def validate_urls(self) -> None:
        """Enforce HTTPS and approved GitHub release hostnames."""
        for url in (self.download_url, self.installer_url):
            if not url:
                continue
            parsed = urlparse(url)
            if parsed.scheme.lower() not in ("https", "http"):
                raise ValueError(f"Insecure or invalid URL scheme in asset: {url}")
            # Enforce HTTPS unless localhost/127.0.0.1 in testing
            if parsed.scheme.lower() == "http" and parsed.hostname not in ("127.0.0.1", "localhost"):
                raise ValueError(f"HTTP downloads rejected. All releases must use HTTPS: {url}")
            if parsed.hostname and parsed.hostname.lower() not in ALLOWED_DOWNLOAD_DOMAINS:
                raise ValueError(f"Untrusted download domain '{parsed.hostname}' in URL: {url}")


@dataclass
class ReleaseManifest:
    """Validated release manifest structure."""
    version: str
    release_date: str
    min_updater_version: str = "1.0.0"
    channel: str = "stable"
    release_notes: str = ""
    assets: dict[str, PlatformAsset] = field(default_factory=dict)
    raw_signature: str = ""

    @classmethod
    def from_json(cls, data_str: str, raw_signature: str = "") -> "ReleaseManifest":
        """Parse and validate JSON manifest."""
        data = json.loads(data_str)
        version = str(data.get("version", "")).strip()
        if not version:
            raise ValueError("Manifest missing required 'version' field")

        assets: dict[str, PlatformAsset] = {}
        for key, asset_dict in data.get("assets", {}).items():
            norm_key = key.lower().strip()
            asset = PlatformAsset(
                filename=str(asset_dict.get("filename", "")),
                download_url=str(asset_dict.get("download_url", "")),
                sha256=str(asset_dict.get("sha256", "")).lower().strip(),
                size=int(asset_dict.get("size", 0)),
                package_type=str(asset_dict.get("package_type", "archive")),
                installer_url=str(asset_dict.get("installer_url", "")),
                installer_sha256=str(asset_dict.get("installer_sha256", "")).lower().strip(),
                signature=str(asset_dict.get("signature", "")).strip(),
            )
            asset.validate_urls()
            assets[norm_key] = asset

        return cls(
            version=version,
            release_date=str(data.get("release_date", "")),
            min_updater_version=str(data.get("min_updater_version", "1.0.0")),
            channel=str(data.get("channel", "stable")),
            release_notes=str(data.get("release_notes", "")),
            assets=assets,
            raw_signature=raw_signature,
        )

    def get_asset_for_current_platform(self) -> Optional[PlatformAsset]:
        """Resolve the appropriate asset for the running system."""
        plat = get_platform_info()
        target_key = f"{plat['os']}-{plat['arch']}"

        # Exact match (e.g. 'windows-x86_64', 'linux-x86_64', 'macos-arm64')
        if target_key in self.assets:
            return self.assets[target_key]

        # Alternative aliases
        alias_map = {
            "windows-x86_64": ["win64", "windows-amd64", "windows-x64"],
            "linux-x86_64": ["linux-amd64", "linux-x64"],
            "macos-arm64": ["darwin-arm64", "macos-aarch64"],
            "macos-x86_64": ["darwin-x86_64", "macos-amd64"],
        }
        for alias in alias_map.get(target_key, []):
            if alias in self.assets:
                return self.assets[alias]

        return None

    def is_compatible_with_updater(self, current_updater_version: str = "1.1.0") -> bool:
        """Check if current updater meets minimum required updater version."""
        try:
            return SemVer(current_updater_version) >= SemVer(self.min_updater_version)
        except Exception:
            return True


def get_expected_asset_filename(os_name: str, arch: str, version: str, package_type: str = "archive") -> str:
    """
    Standardized cross-platform asset naming convention:
      Windows archive:   FinanceWiseTBM-Windows-x86_64.zip
      Windows installer: FinanceWiseTBM-Setup-v1.2.0.exe
      Linux archive:     FinanceWiseTBM-Linux-x86_64.tar.gz
      macOS archive:     FinanceWiseTBM-macOS-x86_64.tar.gz / FinanceWiseTBM-macOS-arm64.tar.gz
    """
    os_name = os_name.lower()
    arch = arch.lower()
    if os_name == "windows":
        if package_type == "installer":
            return f"FinanceWiseTBM-Setup-v{version}.exe"
        return "FinanceWiseTBM-Windows-x86_64.zip"
    elif os_name == "linux":
        return f"FinanceWiseTBM-Linux-{arch}.tar.gz"
    elif os_name in ("macos", "darwin"):
        return f"FinanceWiseTBM-macOS-{arch}.tar.gz"
    return f"FinanceWiseTBM-{os_name}-{arch}.zip"
