# Secure Cross-Platform Auto-Update System Architecture & Operations Manual

## 1. Executive Summary & Architecture Overview

Finance Wise TBM features a secure, cross-platform auto-update system designed for desktop deployments across **Windows, Linux, and macOS**. The system integrates directly with **GitHub Releases**, using semantic versioning, Ed25519 digital signature verification, streaming SHA-256 validation, atomic SQLite database protection, and an out-of-process bootstrapper with automatic rollback.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               GITHUB RELEASES (Cloud)                                  │
│  - Tagged Releases (v1.2.0)                                                            │
│  - Assets: Zip / Tar / Setup Exe                                                       │
│  - Signed Manifest (manifest.json + manifest.json.sig)                                 │
└────────────────────────────────────────┬───────────────────────────────────────────────┘
                                         │ HTTPS (REST API)
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                             DESKTOP APPLICATION (Client)                               │
│                                                                                        │
│  [Startup / Manual Check] ──► Query GitHub API (Non-blocking daemon thread)            │
│  [Version Evaluation]     ──► SemVer comparison (e.g. v1.2.0 > v1.1.0)                 │
│  [Signature Verification] ──► Validate manifest against embedded Ed25519 public key    │
│  [User Notification UX]   ──► Modal: Update Now / Remind Later / Skip Version          │
│  [Streaming Download]     ──► Download to %APPDATA%/FinanceWiseTBM/updates/staging     │
│  [Checksum Verification]  ──► Streaming SHA-256 validation against signed manifest     │
│  [Database Safeguard]     ──► Atomic SQLite Online Backup + PRAGMA integrity_check     │
└────────────────────────────────────────┬───────────────────────────────────────────────┘
                                         │ Spawn detached process & exit cleanly
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        OUT-OF-PROCESS UPDATER BOOTSTRAPPER                             │
│                                                                                        │
│  1. Wait for Main App PID to exit cleanly (never interrupts active transactions)       │
│  2. Create timestamped backup of current application binaries                          │
│  3. Swap application files with verified staged release files                          │
│  4. Run startup health check (`FinanceWiseTBM --health-check`)                         │
│  5. IF HEALTH CHECK PASSES:                                                            │
│     - Launch updated application                                                       │
│     - Clean up staging files only after verified success                               │
│  6. IF HEALTH CHECK FAILS:                                                             │
│     - Safety Rollback: Restore application files from backup directory                 │
│     - Relaunch previous working application (never destroys the only working copy)     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory Structure & File Responsibilities

| File Path | Role & Responsibilities |
| :--- | :--- |
| `chama_system/updater/version.py` | Semantic version parser (`SemVer`), SemVer comparison (`<`, `>`, `==`), installed version detection (`settings.APP_VERSION`), and host OS/architecture detection (`windows`, `linux`, `macos`, `x86_64`, `arm64`). |
| `chama_system/updater/crypto.py` | High-level cryptographic verification. Manages embedded developer public keys, streaming SHA-256 calculation, and Ed25519 signature checks. |
| `chama_system/updater/ed25519_pure.py` | RFC 8032 pure-Python implementation of Ed25519 signature verification and key generation. Operates with zero binary C dependencies using standard library `hashlib`. |
| `chama_system/updater/manifest.py` | Release manifest data model, URL safety validation (strictly enforces HTTPS and approved GitHub release hostnames), and target platform asset resolution. |
| `chama_system/updater/github.py` | GitHub Releases REST API client. Handles release polling, channel filtering (stable vs beta), network timeouts, offline states, and streaming file downloads with speed and progress tracking. |
| `chama_system/updater/storage.py` | User data isolation. Standardizes data directories across Windows (`%APPDATA%`), Linux (`~/.local/share`), and macOS (`~/Library/Application Support`). Implements atomic SQLite Online Backups and `PRAGMA integrity_check` validation. |
| `chama_system/updater/bootstrapper.py` | Standalone out-of-process updater. Coordinates graceful PID termination, binary backups, staging deployment, post-update `--health-check`, and automated rollback on failure. |
| `chama_system/updater/compatibility.py` | Central server / client compatibility checker (`MIN_SUPPORTED_CLIENT_VERSION = '1.0.0'`). Prohibits desktop clients from running migrations against remote central databases and validates that pending transactions are preserved. |
| `chama_system/updater/services.py` | Thread-safe singleton state machine (`UpdateService`) orchestrating update checks, background downloads, user preferences (Skip Version, Remind Later), and bootstrapper handover. |
| `chama_system/updater/views.py` | REST API endpoints for UI interaction: `/updater/check/`, `/updater/download/`, `/updater/progress/`, `/updater/install/`, `/updater/skip/`, `/updater/remind-later/`, and `/api/client-compatibility/`. |
| `chama_system/updater/urls.py` | Django URL routing for the updater module. |
| `chama_system/updater/tests.py` | Comprehensive automated test suite verifying all 15 operational failure modes, cryptographic checks, backups, rollbacks, and API endpoints. |
| `chama_system/templates/updater/update_modal.html` | Polished Bootstrap 5 UI component with animated download progress, real-time speed, release notes, and safety prompts. |
| `scripts/generate_keypair.py` | Developer CLI tool for generating cryptographically secure Ed25519 keypairs. |
| `scripts/build_release_manifest.py` | CI/CD build script that scans compiled binaries, computes SHA-256 checksums, and signs `manifest.json`. |
| `.github/workflows/release.yml` | GitHub Actions workflow executing native multi-platform builds (Windows, Linux, macOS), tests, packaging, and signed GitHub Release publishing. |

---

## 3. Dependencies Added & Justification

| Dependency | Version | Purpose |
| :--- | :--- | :--- |
| `cryptography` | `>=42.0.0` | Optional high-speed C-accelerated Ed25519 signature verification. *(Note: If binary wheels are unavailable on a target machine, `updater.ed25519_pure` provides 100% feature-complete RFC 8032 fallback using Python standard library).* |

---

## 4. Configuration & Environment Variables

Configure these settings in your `.env` or Django settings:

```ini
# GitHub Repository Target
GITHUB_REPO_OWNER=codewitheddy
GITHUB_REPO_NAME=chama

# Update Release Channel
# 'stable' : Only stable releases (drafts and prereleases are filtered out)
# 'beta'   : Includes prereleases (e.g. v1.2.0-beta.1)
UPDATE_CHANNEL=stable

# Trusted Ed25519 Public Key (32 bytes = 64 hex characters)
UPDATER_PUBLIC_KEY=6443eae2622048fc21d49c81c5661b1e1a841295bf1295f6dcdaffadc1387827
```

> **Security Rule:**
> Never embed GitHub write tokens or private signing keys in the desktop application. The application strictly reads public releases over HTTPS and verifies them against the public key.

---

## 5. Release Asset Naming Conventions

To ensure cross-platform compatibility, CI/CD and release tools enforce standard artifact naming:

| Platform & Arch | Package Type | Filename Convention |
| :--- | :--- | :--- |
| **Windows x86_64** | Directory Zip | `FinanceWiseTBM-Windows-x86_64.zip` |
| **Windows x86_64** | Inno Setup Installer | `FinanceWiseTBM-Setup-v{VERSION}.exe` |
| **Linux x86_64** | Tarball | `FinanceWiseTBM-Linux-x86_64.tar.gz` |
| **macOS x86_64** (Intel) | Tarball | `FinanceWiseTBM-macOS-x86_64.tar.gz` |
| **macOS arm64** (Apple Silicon) | Tarball | `FinanceWiseTBM-macOS-arm64.tar.gz` |
| **All Platforms** | Signed Release Manifest | `manifest.json` |
| **All Platforms** | Manifest Digital Signature | `manifest.json.sig` |

### Manifest Format (`manifest.json`)
```json
{
  "version": "1.2.0",
  "release_date": "2026-10-24T12:00:00Z",
  "min_updater_version": "1.0.0",
  "channel": "stable",
  "release_notes": "### New Features\n- Added investment portfolio tracking\n- segregate welfare funds",
  "assets": {
    "windows-x86_64": {
      "filename": "FinanceWiseTBM-Windows-x86_64.zip",
      "download_url": "https://github.com/codewitheddy/chama/releases/download/v1.2.0/FinanceWiseTBM-Windows-x86_64.zip",
      "sha256": "8a3f81e3...",
      "size": 45120000,
      "package_type": "archive",
      "installer_url": "https://github.com/codewitheddy/chama/releases/download/v1.2.0/FinanceWiseTBM-Setup-v1.2.0.exe",
      "installer_sha256": "4b2c19e...",
      "signature": "9d18b4..."
    },
    "linux-x86_64": {
      "filename": "FinanceWiseTBM-Linux-x86_64.tar.gz",
      "download_url": "https://github.com/codewitheddy/chama/releases/download/v1.2.0/FinanceWiseTBM-Linux-x86_64.tar.gz",
      "sha256": "2e7a10f...",
      "size": 42800000,
      "package_type": "archive",
      "signature": "6c4b12..."
    },
    "macos-arm64": {
      "filename": "FinanceWiseTBM-macOS-arm64.tar.gz",
      "download_url": "https://github.com/codewitheddy/chama/releases/download/v1.2.0/FinanceWiseTBM-macOS-arm64.tar.gz",
      "sha256": "7a9e31d...",
      "size": 46200000,
      "package_type": "archive",
      "signature": "1f8e43..."
    }
  }
}
```

---

## 6. Cryptographic Key Management & Release Signing

### 1. Generating a New Keypair
Run the developer key generator:
```bash
python scripts/generate_keypair.py
```
Output:
```
PRIVATE KEY (SEED) : d89e6900aec55f2f944e91b5e9a54cee0e6800d8aed180edf5e5b1e7c5d39d38
PUBLIC KEY         : 6443eae2622048fc21d49c81c5661b1e1a841295bf1295f6dcdaffadc1387827
```

### 2. Provisioning Secrets
1. Go to your GitHub repository: **Settings -> Secrets and variables -> Actions -> New repository secret**.
2. Name: `RELEASE_SIGNING_PRIVATE_KEY`
3. Value: *[Paste the 64-character private key seed]*
4. Update `UPDATER_PUBLIC_KEY` in `chama_system/updater/crypto.py` or `.env`.

---

## 7. How to Build & Publish Releases

### Method A: Automated GitHub Actions (Recommended)
1. Commit and push your changes to `main`.
2. Create and push a semantic version tag:
   ```bash
   git tag v1.2.0
   git push origin v1.2.0
   ```
3. GitHub Actions triggers `.github/workflows/release.yml`:
   - Runs all Django unit tests and system checks.
   - Compiles native binaries on Windows, Linux, and macOS runners using PyInstaller.
   - Builds Windows Inno Setup installer.
   - Calculates SHA-256 checksums.
   - Signs `manifest.json` using the `RELEASE_SIGNING_PRIVATE_KEY` secret.
   - Publishes a signed GitHub Release automatically.

### Method B: Manual / Local Build
1. Build the distribution folder:
   ```cmd
   cd chama_system
   build.bat
   ```
2. Build the signed manifest:
   ```bash
   python scripts/build_release_manifest.py --version 1.2.0 --dist-dir dist_release/ --private-key <YOUR_PRIVATE_KEY>
   ```

---

## 8. Data Preservation, Migration, & Rollback Guarantees

### 1. Local Banking Data Preservation
- Databases (`db.sqlite3`), media uploads (`media/`), and session files are located in `%APPDATA%\FinanceWiseTBM` (Windows), `~/.local/share/FinanceWiseTBM` (Linux), or `~/Library/Application Support/FinanceWiseTBM` (macOS).
- The updater **never** touches or overwrites this directory during application file replacement.

### 2. SQLite Online Backup Before Any Migration
- Before applying any update, `updater.storage.create_safe_sqlite_backup()` calls Python's native SQLite Online Backup API (`src_conn.backup(dest_conn)`).
- This creates an uncorrupted snapshot even if WAL (Write-Ahead Logging) is active.
- Runs `PRAGMA integrity_check;` and verifies that application tables exist before declaring the backup valid.
- Backups are stored in `FinanceWiseTBM/backups/pre_update/`.

### 3. Automatic Rollback Protection
- The bootstrapper backs up existing application files to `<app_dir>_backup_<timestamp>` before swapping files.
- It runs `FinanceWiseTBM --health-check`.
- If the updated application fails to start or encounters an unhandled crash:
  1. The bootstrapper immediately restores the previous application directory.
  2. Relaunches the previous working version.
  3. Logs the failure to `updater_log.txt`.
  4. The user is never left without a working application.

### 4. Online Database Safeguards
- Desktop client updates **never** trigger migrations on a central server database. Central migrations must occur through the server container/CD deployment pipeline.
- If a desktop client connects to an outdated or upgraded server, `/api/client-compatibility/` verifies API version alignment and displays an actionable warning rather than causing silent transaction corruption.

---

## 9. Verification & Testing

To execute the automated test suite:
```bash
cd chama_system
python manage.py test updater
```
All 30 test scenarios execute in under 2 seconds, covering:
- SemVer comparisons and prerelease channel filtering.
- Ed25519 signature validity and tamper rejection.
- Checksum mismatches and insecure download URL rejections.
- Offline and rate-limited API resilience.
- SQLite online backup creation and integrity verification.
- Bootstrapper process replacement and automated rollback.
- Client/server compatibility endpoints.
