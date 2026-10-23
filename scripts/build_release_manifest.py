#!/usr/bin/env python3
"""
Release Manifest Builder & Signer for Finance Wise TBM.
========================================================
Scans built distributable files (zip, tar.gz, setup exe), computes SHA-256 checksums,
generates a structured manifest.json, and signs it using Ed25519 private key.

Usage:
    python scripts/build_release_manifest.py \
        --version 1.2.0 \
        --dist-dir dist_release/ \
        --repo-owner codewitheddy \
        --repo-name chama \
        --private-key <64-hex-chars-or-from-env>
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add chama_system to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "chama_system")))

from updater.crypto import compute_sha256, sign_data
from updater.manifest import get_expected_asset_filename


def build_manifest(
    version: str,
    dist_dir: Path,
    repo_owner: str = "codewitheddy",
    repo_name: str = "chama",
    channel: str = "stable",
    release_notes: str = "",
    private_key_hex: str = "",
) -> tuple[Path, Path]:
    """
    Generate manifest.json and manifest.json.sig in dist_dir.
    """
    dist_dir = Path(dist_dir).resolve()
    if not dist_dir.is_dir():
        raise FileNotFoundError(f"Dist directory does not exist: {dist_dir}")

    sk_hex = private_key_hex or os.environ.get("RELEASE_SIGNING_PRIVATE_KEY", "").strip()
    if not sk_hex:
        raise ValueError("Missing signing private key. Pass --private-key or set RELEASE_SIGNING_PRIVATE_KEY env var.")

    tag = f"v{version.lstrip('v')}"
    base_url = f"https://github.com/{repo_owner}/{repo_name}/releases/download/{tag}"

    assets = {}

    # Define targets to scan for
    platform_targets = [
        ("windows-x86_64", "windows", "x86_64", "FinanceWiseTBM-Windows-x86_64.zip", "archive"),
        ("windows-installer", "windows", "x86_64", f"FinanceWiseTBM-Setup-v{version}.exe", "installer"),
        ("linux-x86_64", "linux", "x86_64", "FinanceWiseTBM-Linux-x86_64.tar.gz", "archive"),
        ("macos-x86_64", "macos", "x86_64", "FinanceWiseTBM-macOS-x86_64.tar.gz", "archive"),
        ("macos-arm64", "macos", "arm64", "FinanceWiseTBM-macOS-arm64.tar.gz", "archive"),
    ]

    for key, os_name, arch, fname, pkg_type in platform_targets:
        file_path = dist_dir / fname
        if file_path.is_file():
            size = file_path.stat().st_size
            sha256_hash = compute_sha256(file_path)
            download_url = f"{base_url}/{fname}"

            # Sign individual asset hash as well
            asset_sig = sign_data(sha256_hash.encode("utf-8"), sk_hex)

            if key == "windows-installer":
                # Link installer into windows-x86_64 if present
                if "windows-x86_64" in assets:
                    assets["windows-x86_64"]["installer_url"] = download_url
                    assets["windows-x86_64"]["installer_sha256"] = sha256_hash
                else:
                    assets["windows-x86_64"] = {
                        "filename": fname,
                        "download_url": download_url,
                        "sha256": sha256_hash,
                        "size": size,
                        "package_type": "installer",
                        "installer_url": download_url,
                        "installer_sha256": sha256_hash,
                        "signature": asset_sig,
                    }
            else:
                target_key = f"{os_name}-{arch}"
                assets[target_key] = {
                    "filename": fname,
                    "download_url": download_url,
                    "sha256": sha256_hash,
                    "size": size,
                    "package_type": pkg_type,
                    "installer_url": "",
                    "installer_sha256": "",
                    "signature": asset_sig,
                }
                print(f"  [+] Packaged asset: {fname} (size: {size} bytes, sha256: {sha256_hash[:12]}...)")

    manifest_data = {
        "version": version,
        "release_date": datetime.now(timezone.utc).isoformat(),
        "min_updater_version": "1.0.0",
        "channel": channel,
        "release_notes": release_notes or f"Finance Wise TBM Release {version}",
        "assets": assets,
    }

    manifest_json_bytes = json.dumps(manifest_data, indent=2).encode("utf-8")

    # Sign the canonical manifest JSON
    sig_hex = sign_data(manifest_json_bytes, sk_hex)

    manifest_path = dist_dir / "manifest.json"
    sig_path = dist_dir / "manifest.json.sig"

    with open(manifest_path, "wb") as f:
        f.write(manifest_json_bytes)

    with open(sig_path, "w", encoding="utf-8") as f:
        f.write(sig_hex)

    print()
    print(f"Manifest written to: {manifest_path}")
    print(f"Signature written to: {sig_path}")
    print(f"Signature (Ed25519) : {sig_hex}")
    return manifest_path, sig_path


def main():
    parser = argparse.ArgumentParser(description="Finance Wise TBM Release Manifest Builder")
    parser.add_argument("--version", required=True, help="Release version (e.g. 1.2.0)")
    parser.add_argument("--dist-dir", required=True, help="Directory containing built packages")
    parser.add_argument("--repo-owner", default="codewitheddy", help="GitHub repository owner")
    parser.add_argument("--repo-name", default="chama", help="GitHub repository name")
    parser.add_argument("--channel", default="stable", choices=["stable", "beta"], help="Release channel")
    parser.add_argument("--release-notes", default="", help="Release notes text or markdown")
    parser.add_argument("--private-key", default="", help="64-character hex Ed25519 private key seed")

    args = parser.parse_args()

    build_manifest(
        version=args.version,
        dist_dir=Path(args.dist_dir),
        repo_owner=args.repo_owner,
        repo_name=args.repo_name,
        channel=args.channel,
        release_notes=args.release_notes,
        private_key_hex=args.private_key,
    )


if __name__ == "__main__":
    main()
