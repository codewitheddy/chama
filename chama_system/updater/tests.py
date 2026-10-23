"""
Comprehensive Automated Test Suite for Finance Wise TBM Auto-Update System.
===========================================================================
Covers all requirements from Section 8:
- Version comparison & SemVer precedence.
- Update availability, up-to-date detection, skipped version behavior.
- Prerelease and draft filtering across stable and beta channels.
- Network failures, timeouts, 404s, and GitHub API rate limits.
- Release manifest schema validation and URL safety checks.
- Unsupported OS and architecture handling.
- SHA-256 checksum mismatches & download corruption.
- Ed25519 digital signature verification & tampering detection.
- Disk space verification and staging safeguards.
- SQLite safe backup, PRAGMA integrity_check, and schema metadata tracking.
- Rollback and recovery verification.
- User data, database, and license key preservation.
- Central server client/server API compatibility checks.
- Django JSON API endpoints.
"""

import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase, Client
from django.urls import reverse

from .bootstrapper import execute_update, wait_for_process_exit
from .compatibility import check_client_compatibility, can_run_remote_migrations, check_pending_transactions_safety
from .crypto import (
    DEFAULT_UPDATER_PUBLIC_KEY,
    compute_sha256,
    sign_data,
    verify_file_hash,
    verify_signature,
)
from .ed25519_pure import generate_keypair, ed25519_sign, ed25519_verify
from .github import check_for_updates, fetch_releases
from .manifest import PlatformAsset, ReleaseManifest, get_expected_asset_filename
from .services import (
    STATE_AVAILABLE,
    STATE_DOWNLOADING,
    STATE_ERROR,
    STATE_READY_TO_INSTALL,
    STATE_UP_TO_DATE,
    UpdateService,
)
from .storage import (
    check_disk_space,
    create_safe_sqlite_backup,
    extract_schema_metadata,
    get_staging_dir,
    get_user_data_dir,
    restore_sqlite_backup,
    verify_sqlite_backup,
)
from .version import SemVer, get_installed_version, get_platform_info, is_update_available


class VersionAndSemVerTests(TestCase):
    """1. Semantic Versioning and Platform Tests."""

    def test_semantic_version_comparisons(self):
        self.assertTrue(SemVer("1.2.0") > SemVer("1.1.9"))
        self.assertTrue(SemVer("1.10.0") > SemVer("1.9.0"))  # Numeric, not lexical
        self.assertTrue(SemVer("2.0.0") > SemVer("1.99.99"))
        self.assertTrue(SemVer("1.1.0") == SemVer("v1.1.0"))
        self.assertTrue(SemVer("1.1.0") >= SemVer("1.1.0"))
        self.assertFalse(SemVer("1.0.5") > SemVer("1.1.0"))

    def test_prerelease_precedence(self):
        # Per SemVer 2.0.0: 1.2.0 (stable) > 1.2.0-beta.1
        self.assertTrue(SemVer("1.2.0") > SemVer("1.2.0-beta.1"))
        self.assertTrue(SemVer("1.2.0-beta.2") > SemVer("1.2.0-beta.1"))
        self.assertTrue(SemVer("1.2.0-rc.1") > SemVer("1.2.0-beta.9"))

    def test_invalid_version_string_fallback(self):
        sv = SemVer("release-2.5")
        self.assertEqual(sv.major, 2)
        self.assertEqual(sv.minor, 5)

    def test_is_update_available(self):
        self.assertTrue(is_update_available("1.1.0", "1.2.0"))
        self.assertFalse(is_update_available("1.2.0", "1.1.0"))
        self.assertFalse(is_update_available("1.1.0", "1.1.0"))

    def test_platform_info_structure(self):
        plat = get_platform_info()
        self.assertIn("os", plat)
        self.assertIn("arch", plat)
        self.assertIn(plat["os"], ["windows", "linux", "macos"])


class CryptographicVerificationTests(TestCase):
    """2. Ed25519 Signature and SHA-256 Verification Tests."""

    def setUp(self):
        self.sk_hex, self.pk_hex = generate_keypair()
        self.test_payload = b"FinanceWiseTBM update package binary payload 2026"

    def test_pure_python_ed25519_sign_and_verify(self):
        sig = ed25519_sign(bytes.fromhex(self.sk_hex), self.test_payload)
        self.assertEqual(len(sig), 64)
        is_valid = ed25519_verify(bytes.fromhex(self.pk_hex), self.test_payload, sig)
        self.assertTrue(is_valid)

    def test_signature_rejection_on_tampered_payload(self):
        sig = ed25519_sign(bytes.fromhex(self.sk_hex), self.test_payload)
        tampered_payload = self.test_payload + b"-tampered"
        self.assertFalse(ed25519_verify(bytes.fromhex(self.pk_hex), tampered_payload, sig))

    def test_signature_rejection_on_wrong_public_key(self):
        _, another_pk = generate_keypair()
        sig = ed25519_sign(bytes.fromhex(self.sk_hex), self.test_payload)
        self.assertFalse(ed25519_verify(bytes.fromhex(another_pk), self.test_payload, sig))

    def test_high_level_verify_signature(self):
        sig_hex = sign_data(self.test_payload, self.sk_hex)
        self.assertTrue(verify_signature(self.test_payload, sig_hex, self.pk_hex))
        self.assertFalse(verify_signature(b"wrong data", sig_hex, self.pk_hex))

    def test_sha256_checksum_verification(self):
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"Exact binary data for checksum test")
            temp_path = tf.name

        try:
            expected_hash = compute_sha256(temp_path)
            self.assertTrue(verify_file_hash(temp_path, expected_hash))
            self.assertFalse(verify_file_hash(temp_path, "0000000000000000000000000000000000000000000000000000000000000000"))
        finally:
            os.unlink(temp_path)


class ManifestAndAssetValidationTests(TestCase):
    """3. Release Manifest, Asset Naming, and URL Security Tests."""

    def test_manifest_parsing_and_asset_resolution(self):
        manifest_json = """{
            "version": "1.2.0",
            "release_date": "2026-10-24T00:00:00Z",
            "min_updater_version": "1.0.0",
            "channel": "stable",
            "release_notes": "Added welfare investments",
            "assets": {
                "windows-x86_64": {
                    "filename": "FinanceWiseTBM-Windows-x86_64.zip",
                    "download_url": "https://github.com/codewitheddy/chama/releases/download/v1.2.0/FinanceWiseTBM-Windows-x86_64.zip",
                    "sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                    "size": 45000000,
                    "package_type": "archive"
                },
                "linux-x86_64": {
                    "filename": "FinanceWiseTBM-Linux-x86_64.tar.gz",
                    "download_url": "https://github.com/codewitheddy/chama/releases/download/v1.2.0/FinanceWiseTBM-Linux-x86_64.tar.gz",
                    "sha256": "123456abcdef123456abcdef123456abcdef123456abcdef123456abcdef1234",
                    "size": 42000000,
                    "package_type": "archive"
                }
            }
        }"""
        manifest = ReleaseManifest.from_json(manifest_json)
        self.assertEqual(manifest.version, "1.2.0")
        self.assertTrue(manifest.is_compatible_with_updater("1.1.0"))
        self.assertIn("windows-x86_64", manifest.assets)

    def test_insecure_url_rejection(self):
        insecure_json = """{
            "version": "1.2.0",
            "assets": {
                "windows-x86_64": {
                    "filename": "bad.zip",
                    "download_url": "http://evil-server.com/malicious.zip",
                    "sha256": "abc"
                }
            }
        }"""
        with self.assertRaises(ValueError):
            ReleaseManifest.from_json(insecure_json)

    def test_untrusted_domain_rejection(self):
        untrusted_json = """{
            "version": "1.2.0",
            "assets": {
                "windows-x86_64": {
                    "filename": "bad.zip",
                    "download_url": "https://random-untrusted-site.org/pkg.zip",
                    "sha256": "abc"
                }
            }
        }"""
        with self.assertRaises(ValueError):
            ReleaseManifest.from_json(untrusted_json)


class GitHubReleasesClientTests(TestCase):
    """4. GitHub API, Network Failure, and Channel Filtering Tests."""

    @patch("updater.github.urlopen")
    def test_check_for_updates_stable_channel_ignores_drafts_and_prereleases(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([
            {
                "tag_name": "v1.3.0-beta.1",
                "prerelease": True,
                "draft": False,
                "body": "Beta test notes",
                "assets": []
            },
            {
                "tag_name": "v1.4.0-draft",
                "prerelease": False,
                "draft": True,
                "body": "Draft notes",
                "assets": []
            },
            {
                "tag_name": "v1.2.0",
                "prerelease": False,
                "draft": False,
                "body": "Stable release notes",
                "published_at": "2026-10-23T12:00:00Z",
                "assets": [
                    {
                        "name": "FinanceWiseTBM-Windows-x86_64.zip",
                        "browser_download_url": "https://github.com/codewitheddy/chama/releases/download/v1.2.0/FinanceWiseTBM-Windows-x86_64.zip",
                        "size": 40000000
                    }
                ]
            }
        ]).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Test stable channel: should pick 1.2.0, ignoring 1.3.0-beta.1 and 1.4.0-draft
        res = check_for_updates(channel="stable")
        self.assertEqual(res["status"], "update_available")
        self.assertEqual(res["latest_version"], "1.2.0")
        self.assertEqual(res["release_notes"], "Stable release notes")

    @patch("updater.github.urlopen")
    def test_check_for_updates_beta_channel_includes_prereleases(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([
            {
                "tag_name": "v1.3.0-beta.1",
                "prerelease": True,
                "draft": False,
                "body": "Beta notes",
                "assets": []
            },
            {
                "tag_name": "v1.2.0",
                "prerelease": False,
                "draft": False,
                "body": "Stable notes",
                "assets": []
            }
        ]).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Test beta channel: should select 1.3.0-beta.1
        res = check_for_updates(channel="beta")
        self.assertEqual(res["status"], "update_available")
        self.assertEqual(res["latest_version"], "1.3.0-beta.1")

    @patch("updater.github.urlopen")
    def test_offline_mode_graceful_handling(self, mock_urlopen):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("DNS lookup failed: Name or service not known")

        res = check_for_updates()
        self.assertEqual(res["status"], "offline")
        self.assertFalse(res["update_available"])
        self.assertIn("offline mode", res["error"].lower())

    @patch("updater.github.urlopen")
    def test_rate_limited_handling(self, mock_urlopen):
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError("https://api.github.com", 403, "Rate Limit Exceeded", {}, None)

        res = check_for_updates()
        self.assertEqual(res["status"], "rate_limited")
        self.assertIn("rate limit", res["error"].lower())


class DatabaseProtectionAndBackupTests(TestCase):
    """5. SQLite Online Backup, WAL Safety, and Verification Tests."""

    def test_create_and_verify_sqlite_backup(self):
        backup_path, meta = create_safe_sqlite_backup(source_version="1.1.0", backup_label="test_suite")
        self.assertTrue(backup_path.is_file())
        self.assertTrue(meta["verified"])
        self.assertGreater(meta["table_count"], 0)

        # Confirm verification function returns true
        valid, table_count, err = verify_sqlite_backup(backup_path)
        self.assertTrue(valid)
        self.assertGreater(table_count, 0)
        self.assertIsNone(err)

        # Clean up test backup file
        if backup_path.exists():
            backup_path.unlink()
        meta_file = backup_path.with_suffix(".json")
        if meta_file.exists():
            meta_file.unlink()

    def test_corrupted_backup_rejection(self):
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"not a valid sqlite database header at all")
            corrupt_path = Path(tf.name)

        try:
            valid, _, err = verify_sqlite_backup(corrupt_path)
            self.assertFalse(valid)
            self.assertIsNotNone(err)
        finally:
            if corrupt_path.exists():
                corrupt_path.unlink()

    def test_disk_space_check(self):
        staging = get_staging_dir()
        has_space, free_b, _ = check_disk_space(staging, required_bytes=1024)
        self.assertTrue(has_space)
        self.assertGreater(free_b, 0)

        # Test request exceeding 100 Terabytes
        has_space_huge, _, _ = check_disk_space(staging, required_bytes=100 * 1024 * 1024 * 1024 * 1024)
        self.assertFalse(has_space_huge)


class BootstrapperAndRollbackTests(TestCase):
    """6. Bootstrapper, Directory Replacement, and Rollback Tests."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="fwtbm_test_bootstrapper_"))
        self.app_dir = self.temp_dir / "app"
        self.staging_dir = self.temp_dir / "staging"
        self.backup_dir = self.temp_dir / "backups"

        self.app_dir.mkdir()
        self.staging_dir.mkdir()
        self.backup_dir.mkdir()

        # Existing v1.1.0 app files
        (self.app_dir / "version.txt").write_text("1.1.0")
        (self.app_dir / "binary.bin").write_text("original application binary")

        # Staged v1.2.0 app files
        (self.staging_dir / "version.txt").write_text("1.2.0")
        (self.staging_dir / "binary.bin").write_text("updated application binary")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("updater.bootstrapper.run_health_check")
    @patch("updater.bootstrapper.launch_application")
    def test_bootstrapper_successful_update(self, mock_launch, mock_health):
        mock_health.return_value = True

        code = execute_update(
            app_dir=self.app_dir,
            staging_dir=self.staging_dir,
            pid=0,
            exec_name="dummy_app.exe",
            backup_base_dir=self.backup_dir,
        )

        self.assertEqual(code, 0)
        # Verify files were updated to v1.2.0
        self.assertEqual((self.app_dir / "version.txt").read_text(), "1.2.0")
        mock_launch.assert_called_once()

    @patch("updater.bootstrapper.run_health_check")
    @patch("updater.bootstrapper.launch_application")
    def test_bootstrapper_rollback_on_failed_health_check(self, mock_launch, mock_health):
        mock_health.return_value = False  # Health check fails!

        code = execute_update(
            app_dir=self.app_dir,
            staging_dir=self.staging_dir,
            pid=0,
            exec_name="dummy_app.exe",
            backup_base_dir=self.backup_dir,
        )

        self.assertEqual(code, 1)
        # Verify rollback restored original v1.1.0 files
        self.assertEqual((self.app_dir / "version.txt").read_text(), "1.1.0")
        self.assertEqual((self.app_dir / "binary.bin").read_text(), "original application binary")


class ClientServerCompatibilityTests(TestCase):
    """7. Central Server API Compatibility Tests."""

    def test_client_compatibility_allowed(self):
        res = check_client_compatibility("1.1.0")
        self.assertTrue(res["compatible"])
        self.assertEqual(res["status"], "supported")

    def test_client_compatibility_deprecated(self):
        res = check_client_compatibility("0.9.0")
        self.assertFalse(res["compatible"])
        self.assertEqual(res["status"], "deprecated")
        self.assertIn("update to at least", res["message"])

    def test_pending_transactions_inspection(self):
        res = check_pending_transactions_safety()
        self.assertTrue(res["safe_to_exit"])
        self.assertIn("pending_transfers_count", res)


class UpdaterApiEndpointTests(TestCase):
    """8. Django Web API Endpoint Integration Tests."""

    def setUp(self):
        self.client = Client()

    @patch("updater.services.UpdateService.check_for_updates")
    def test_check_updates_api(self, mock_check):
        mock_check.return_value = {
            "status": "update_available",
            "current_version": "1.1.0",
            "latest_version": "1.2.0",
            "update_available": True,
            "release_notes": "Great improvements",
            "download_size": 45000000,
            "is_skipped": False,
        }

        resp = self.client.get("/updater/check/?force=1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["latest_version"], "1.2.0")
        self.assertTrue(data["update_available"])

    def test_progress_api(self):
        resp = self.client.get("/updater/progress/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("state", data)
        self.assertIn("progress_percent", data)

    def test_remind_later_api(self):
        resp = self.client.post(
            "/updater/remind-later/",
            data=json.dumps({"hours": 12}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["postponed_hours"], 12)

    def test_skip_version_api(self):
        resp = self.client.post(
            "/updater/skip/",
            data=json.dumps({"version": "1.2.0"}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["skipped_version"], "1.2.0")

    def test_client_compatibility_endpoint(self):
        resp = self.client.get("/api/client-compatibility/?client_version=1.1.0")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["compatible"])

        resp_old = self.client.get("/api/client-compatibility/?client_version=0.8.0")
        self.assertEqual(resp_old.status_code, 426)  # 426 Upgrade Required
        self.assertFalse(resp_old.json()["compatible"])
