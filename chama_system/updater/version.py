"""
Semantic versioning and platform resolution for Finance Wise TBM.
==================================================================
Handles strict semantic version comparisons (e.g. 1.2.0 > 1.1.9, 1.2.0 > 1.2.0-beta.1),
installed version tracking, and operating system / CPU architecture detection.
"""

import platform
import re
import sys
from typing import Any, Tuple


class SemVer:
    """
    Semantic Version representation adhering to SemVer 2.0.0.
    Correctly compares versions numerically and handles prereleases.
    """

    # Matches: [v]MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
    PATTERN = re.compile(
        r"^v?(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?"
        r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
        r"(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
    )

    def __init__(self, version_str: str):
        self.raw = str(version_str).strip()
        match = self.PATTERN.match(self.raw)
        if not match:
            # Fallback for simple numeric or irregular version strings
            digits = re.findall(r"\d+", self.raw)
            if digits:
                self.major = int(digits[0])
                self.minor = int(digits[1]) if len(digits) > 1 else 0
                self.patch = int(digits[2]) if len(digits) > 2 else 0
                self.prerelease = ""
                self.build = ""
            else:
                raise ValueError(f"Invalid semantic version string: '{version_str}'")
        else:
            self.major = int(match.group("major"))
            self.minor = int(match.group("minor"))
            self.patch = int(match.group("patch") or 0)
            self.prerelease = match.group("prerelease") or ""
            self.build = match.group("build") or ""

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    def _cmp_key(self) -> Tuple[int, int, int, int, Any]:
        """
        Comparison key.
        Per SemVer spec:
        A normal version has higher precedence than a prerelease version with the same major.minor.patch.
        Example: 1.0.0 > 1.0.0-alpha.
        """
        # When prerelease is empty, sort indicator is 1 (higher precedence)
        # When prerelease is present, sort indicator is 0 (lower precedence)
        if not self.prerelease:
            return (self.major, self.minor, self.patch, 1, ())

        # Split prerelease into dot-separated identifiers
        parsed_pre = []
        for part in self.prerelease.split("."):
            if part.isdigit():
                parsed_pre.append((0, int(part)))  # Numeric identifiers sort numerically
            else:
                parsed_pre.append((1, part))       # String identifiers sort lexically
        return (self.major, self.minor, self.patch, 0, tuple(parsed_pre))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, SemVer):
            try:
                other = SemVer(str(other))
            except Exception:
                return False
        return self._cmp_key() == other._cmp_key()

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, SemVer):
            other = SemVer(str(other))
        return self._cmp_key() < other._cmp_key()

    def __le__(self, other: Any) -> bool:
        return self < other or self == other

    def __gt__(self, other: Any) -> bool:
        return not (self <= other)

    def __ge__(self, other: Any) -> bool:
        return not (self < other)

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            s += f"-{self.prerelease}"
        return s

    def __repr__(self) -> str:
        return f"<SemVer {self}>"


def get_installed_version() -> SemVer:
    """Return the currently installed application version as a SemVer instance."""
    try:
        from django.conf import settings
        raw_version = getattr(settings, "APP_VERSION", "1.1.0")
    except Exception:
        raw_version = "1.1.0"
    return SemVer(raw_version)


def get_platform_info() -> dict[str, str]:
    """
    Detect the host operating system and CPU architecture.
    Returns normalized dictionary:
      {'os': 'windows'|'linux'|'macos', 'arch': 'x86_64'|'arm64'}
    """
    sys_name = platform.system().lower()
    if sys_name == "darwin":
        os_name = "macos"
    elif sys_name == "windows":
        os_name = "windows"
    elif sys_name == "linux":
        os_name = "linux"
    else:
        os_name = sys_name

    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64", "x64"):
        arch = "x86_64"
    elif machine in ("arm64", "aarch64", "armv8"):
        arch = "arm64"
    elif machine in ("i386", "i686", "x86"):
        arch = "x86"
    else:
        arch = machine

    return {
        "os": os_name,
        "arch": arch,
        "raw_system": platform.system(),
        "raw_machine": platform.machine(),
    }


def is_update_available(installed_version: str, candidate_version: str) -> bool:
    """Return True if candidate_version is strictly newer than installed_version."""
    try:
        inst = SemVer(installed_version) if not isinstance(installed_version, SemVer) else installed_version
        cand = SemVer(candidate_version) if not isinstance(candidate_version, SemVer) else candidate_version
        return cand > inst
    except Exception:
        return False
