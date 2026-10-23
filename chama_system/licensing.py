"""
Finance Wise TBM — Offline Licensing
======================================
Machine-locked activation using HMAC-SHA256.

Flow
----
1.  get_machine_id()   → derives a stable, hardware-bound ID for this PC.
2.  generate_key()     → YOU run this offline to produce a key for a client.
3.  verify_key()       → validates a key against a machine ID.
4.  is_activated()     → fast boolean check used by desktop.py on startup.
5.  save_key() /
    load_key()         → persists and loads the key across multiple user
                         profiles (%APPDATA%, %ProgramData%, Registry).

Secret
------
LICENSOR_SECRET is embedded at build time. Change it to something only you
know before distributing. Never share or commit this value.
"""

import ctypes
import hashlib
import hmac
import os
import platform
import re
import sys
from pathlib import Path

# ── YOUR SECRET — change before building the final exe ───────────────────────
# Use a long random string, e.g.:
#   python -c "import secrets; print(secrets.token_hex(32))"
LICENSOR_SECRET = b"fw-tbm-super-secret-change-me-before-build-2024"
# ─────────────────────────────────────────────────────────────────────────────

_KEY_VERSION    = "FW1"          # prefix so you can rev the algo later
_KEY_FILE       = "license.key"
_SYSTEM_ID_FILE = "system.id"


# ── String sanitiser ─────────────────────────────────────────────────────────

def _clean(s: str) -> str:
    """Strip whitespace and non-alphanumeric chars for stable hashing."""
    if not s:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(s)).upper()


# ── Windows Registry & Hardware helpers (instant, in-memory, no subprocesses) ─

def _get_win_reg(hive, subkey: str, name: str) -> str:
    """Read a registry string value safely, handling 32-bit and 64-bit views."""
    if platform.system() != "Windows":
        return ""
    try:
        import winreg
        for flags in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ):
            try:
                k = winreg.OpenKey(hive, subkey, 0, flags)
                val, _ = winreg.QueryValueEx(k, name)
                winreg.CloseKey(k)
                if isinstance(val, (list, tuple)):
                    val = " ".join(str(x) for x in val)
                return str(val).strip()
            except Exception:
                pass
    except Exception:
        pass
    return ""


def _get_system_volume_serial() -> str:
    """Return the volume serial number of the Windows system drive."""
    if platform.system() != "Windows":
        return ""
    try:
        drive = os.environ.get("SystemDrive", "C:")
        if not drive.endswith("\\"):
            drive += "\\"
        serial = ctypes.c_ulong()
        res = ctypes.windll.kernel32.GetVolumeInformationW(
            drive, None, 0, ctypes.byref(serial), None, None, None, 0
        )
        if res and serial.value:
            return f"{serial.value:08X}"
    except Exception:
        pass
    return ""


# ── Machine fingerprint ───────────────────────────────────────────────────────

def get_machine_id() -> str:
    """
    Return a 100% deterministic, hardware-bound machine identifier (32-char hex).

    Sources used (Windows):
      1. MachineGuid from Windows Registry — generated once during OS install,
         permanent across updates, reboots, network changes, and offline states.
      2. Motherboard / Baseboard model from BIOS registry — hardware-bound.
      3. CPU architecture identifier from CPU registry — hardware-bound.
      4. System volume serial number — partition-bound.

    Never uses uuid.getnode() (which randomises offline and changes on adapter switch)
    and never calls external PowerShell or wmic commands on every start.
    """
    parts = []

    if platform.system() == "Windows":
        import winreg

        # 1. Windows MachineGuid (unique per OS installation)
        guid = _get_win_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            "MachineGuid",
        )
        if guid:
            parts.append(_clean(guid))

        # 2. Motherboard / Baseboard or System Model
        mb = _get_win_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\BIOS",
            "BaseBoardProduct",
        )
        if not mb or _clean(mb) in ("", "DEFAULTSTRING", "TOBEFILLED", "NONE", "0", "NOTSPECIFIED"):
            mb = _get_win_reg(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\BIOS",
                "SystemProductName",
            )
        if mb and _clean(mb) not in ("", "DEFAULTSTRING", "TOBEFILLED", "NONE", "0", "NOTSPECIFIED"):
            parts.append(_clean(mb))

        # 3. CPU identifier
        cpu = _get_win_reg(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            "Identifier",
        )
        if cpu:
            parts.append(_clean(cpu))

        # 4. System drive serial
        vol = _get_system_volume_serial()
        if vol:
            parts.append(_clean(vol))

    elif platform.system() == "Linux":
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            if os.path.exists(p):
                try:
                    parts.append(_clean(Path(p).read_text()))
                    break
                except Exception:
                    pass

    elif platform.system() == "Darwin":
        try:
            import subprocess
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                text=True, timeout=2,
            )
            m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            if m:
                parts.append(_clean(m.group(1)))
        except Exception:
            pass

    # Universal fallback if all hardware queries failed
    if not parts:
        parts.append(_clean(platform.node()))

    combined = "|".join(p for p in parts if p)
    digest = hashlib.sha256(combined.encode()).hexdigest()
    return digest[:32].upper()


def _get_legacy_machine_id() -> str:
    """Fallback generator using previous heuristic (with strict 1.5s timeout) for migration."""
    parts = []
    if platform.system() == "Windows":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(k, "MachineGuid")
            winreg.CloseKey(k)
            parts.append(_clean(str(guid)))
        except Exception:
            pass

        try:
            import subprocess
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-Command", "(Get-WmiObject Win32_BaseBoard).SerialNumber"],
                capture_output=True, text=True, timeout=1.5,
            )
            out = res.stdout.strip()
            if out and _clean(out) not in ("", "DEFAULT", "NONE", "TOFILL", "0", "TOBEFILLED", "NOTSPECIFIED"):
                parts.append(_clean(out))
        except Exception:
            pass

    try:
        import uuid
        parts.append(_clean(platform.node()))
        parts.append(_clean(hex(uuid.getnode())))
    except Exception:
        pass

    if not parts:
        return ""
    combined = "|".join(p for p in parts if p)
    return hashlib.sha256(combined.encode()).hexdigest()[:32].upper()


# ── Key generation (run on YOUR machine, not the client's) ───────────────────

def generate_key(machine_id: str) -> str:
    """
    Generate an activation key for the given machine_id.

    Run this yourself, e.g.:
        python licensing.py generate <machine_id>

    The key is deterministic — same machine_id always yields the same key.
    """
    machine_id = machine_id.strip().upper()
    sig = hmac.new(
        LICENSOR_SECRET,
        f"{_KEY_VERSION}:{machine_id}".encode(),
        hashlib.sha256,
    ).hexdigest()[:40].upper()

    # Format as XXXXX-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX (5×8)
    chunks = [sig[i:i+5] for i in range(0, 40, 5)]
    return "-".join(chunks)


# ── Verification ──────────────────────────────────────────────────────────────

def verify_key(machine_id: str, key: str) -> bool:
    """Return True if key is valid for this machine_id."""
    if not machine_id or not key:
        return False
    expected = generate_key(machine_id)
    # constant-time compare
    return hmac.compare_digest(
        expected.replace("-", "").strip().upper(),
        key.replace("-", "").strip().upper(),
    )


# ── Persistence (Multi-location: %APPDATA%, %ProgramData%, Registry) ──────────

def _primary_dir() -> Path:
    """Return the primary user-level directory for FinanceWiseTBM."""
    base = (
        os.environ.get("APPDATA")
        or os.environ.get("USERPROFILE")
        or str(Path.home())
    )
    d = Path(base) / "FinanceWiseTBM"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def _key_path() -> Path:
    """Primary license key path."""
    return _primary_dir() / _KEY_FILE


def _candidate_key_paths() -> list:
    """
    Return all locations to search for the license key in order of priority:
      1. Primary user APPDATA folder
      2. Machine-wide ProgramData folder (shared across all users and admin)
      3. LocalAppData folder
      4. Database directory (if DESKTOP_DB_PATH is specified)
      5. User home folder
      6. Next to executable (portable installations / legacy)
    """
    paths = [_key_path()]

    # ProgramData (CommonApplicationData) — vital when installed by admin but run by user
    prog_data = os.environ.get("ProgramData", r"C:\ProgramData")
    if prog_data:
        paths.append(Path(prog_data) / "FinanceWiseTBM" / _KEY_FILE)

    # Local AppData
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        paths.append(Path(local_appdata) / "FinanceWiseTBM" / _KEY_FILE)

    # Database directory if configured
    db_path = os.environ.get("DESKTOP_DB_PATH")
    if db_path:
        paths.append(Path(db_path).parent / _KEY_FILE)

    # Portable exe directory
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        paths.append(exe_dir / _KEY_FILE)
        paths.append(exe_dir / "_internal" / _KEY_FILE)

    # Clean duplicates while preserving order
    seen = set()
    result = []
    for p in paths:
        try:
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                result.append(p)
        except Exception:
            if p not in seen:
                seen.add(p)
                result.append(p)
    return result


def _read_registry_key() -> str:
    """Read stored license key from Windows registry if available."""
    if platform.system() != "Windows":
        return ""
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for flags in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ):
                try:
                    k = winreg.OpenKey(hive, r"Software\FinanceWiseTBM", 0, flags)
                    val, _ = winreg.QueryValueEx(k, "LicenseKey")
                    winreg.CloseKey(k)
                    if val and str(val).strip():
                        return str(val).strip().upper()
                except Exception:
                    pass
    except Exception:
        pass
    return ""


def _write_registry_key(key: str):
    """Write license key to HKCU (and HKLM if elevated) in Windows registry."""
    if platform.system() != "Windows":
        return
    try:
        import winreg
        # Always write to HKCU (standard user accessible)
        try:
            k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\FinanceWiseTBM")
            winreg.SetValueEx(k, "LicenseKey", 0, winreg.REG_SZ, key)
            winreg.CloseKey(k)
        except Exception:
            pass

        # Try writing to HKLM (succeeds if running as administrator)
        try:
            k = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, r"Software\FinanceWiseTBM")
            winreg.SetValueEx(k, "LicenseKey", 0, winreg.REG_SZ, key)
            winreg.CloseKey(k)
        except Exception:
            pass
    except Exception:
        pass


def save_key(key: str):
    """
    Persist an activation key across all storage tiers:
      - %APPDATA%/FinanceWiseTBM/license.key
      - %ProgramData%/FinanceWiseTBM/license.key (machine-wide)
      - Registry (HKCU and HKLM)
      - Also writes system.id alongside for user reference
    """
    norm_key = key.strip().upper()
    current_mid = get_machine_id()

    # 1. Primary path
    try:
        p = _key_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(norm_key)
        # Write system.id for diagnostics
        (p.parent / _SYSTEM_ID_FILE).write_text(current_mid)
    except Exception:
        pass

    # 2. ProgramData (machine-wide for all users on this PC)
    try:
        prog_data = os.environ.get("ProgramData", r"C:\ProgramData")
        if prog_data:
            pd_dir = Path(prog_data) / "FinanceWiseTBM"
            pd_dir.mkdir(parents=True, exist_ok=True)
            (pd_dir / _KEY_FILE).write_text(norm_key)
            (pd_dir / _SYSTEM_ID_FILE).write_text(current_mid)
    except Exception:
        pass

    # 3. LocalAppData
    try:
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            la_dir = Path(local_app) / "FinanceWiseTBM"
            la_dir.mkdir(parents=True, exist_ok=True)
            (la_dir / _KEY_FILE).write_text(norm_key)
    except Exception:
        pass

    # 4. Database directory if set
    try:
        db_path = os.environ.get("DESKTOP_DB_PATH")
        if db_path:
            db_dir = Path(db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)
            (db_dir / _KEY_FILE).write_text(norm_key)
    except Exception:
        pass

    # 5. Windows Registry
    _write_registry_key(norm_key)


def load_key() -> str:
    """
    Load stored key from files or registry.
    If found in a secondary location, syncs it to the primary location.
    """
    # 1. Check file locations in priority order
    for candidate in _candidate_key_paths():
        try:
            if candidate.exists():
                key = candidate.read_text().strip().upper()
                if key:
                    # Sync to primary if read from elsewhere
                    if candidate != _key_path():
                        try:
                            _key_path().write_text(key)
                        except Exception:
                            pass
                    return key
        except Exception:
            pass

    # 2. Check Windows Registry
    reg_key = _read_registry_key()
    if reg_key:
        try:
            save_key(reg_key)
        except Exception:
            pass
        return reg_key

    return ""


def is_activated() -> bool:
    """Return True if this machine has a valid activation key stored."""
    stored_key = load_key()
    if not stored_key:
        return False

    mid = get_machine_id()
    if verify_key(mid, stored_key):
        return True

    # Check legacy migration heuristic
    legacy_mid = _get_legacy_machine_id()
    if legacy_mid and verify_key(legacy_mid, stored_key):
        # Found valid legacy key! Migrate to stable key
        try:
            new_key = generate_key(mid)
            save_key(new_key)
        except Exception:
            pass
        return True

    return False


# ── CLI helpers (for YOU — the licensor) ─────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Finance Wise TBM — License Tool")
    sub = parser.add_subparsers(dest="cmd")

    gen = sub.add_parser("generate", help="Generate a key for a machine ID")
    gen.add_argument("machine_id", help="Machine ID from the activation screen")

    sub.add_parser("machine-id", help="Print this machine's ID")
    sub.add_parser("check",      help="Check if this machine is activated")

    args = parser.parse_args()

    if args.cmd == "generate":
        mid = args.machine_id.strip().upper()
        key = generate_key(mid)
        print(f"\nMachine ID : {mid}")
        print(f"License Key: {key}\n")

    elif args.cmd == "machine-id":
        print(get_machine_id())

    elif args.cmd == "check":
        mid = get_machine_id()
        key = load_key()
        print(f"Machine ID : {mid}")
        print(f"Stored Key : {key or '(none)'}")
        print(f"Activated  : {is_activated()}")

    else:
        parser.print_help()

