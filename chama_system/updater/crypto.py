"""
Cryptographic verification and hashing layer for Finance Wise TBM updates.
==========================================================================
Provides:
1. Ed25519 digital signature verification (via `cryptography` when present,
   with pure-Python RFC 8032 fallback).
2. Streaming SHA-256 checksum calculation and verification.
3. Strict authenticity checks preventing MITM attacks or checksum tampering.
"""

import hashlib
import os
from pathlib import Path
from typing import Union

# Embedded default developer public key (32 bytes = 64 hex characters)
# Developers can override via environment variable UPDATER_PUBLIC_KEY
# or Django setting `UPDATER_PUBLIC_KEY`.
DEFAULT_UPDATER_PUBLIC_KEY = (
    "6443eae2622048fc21d49c81c5661b1e1a841295bf1295f6dcdaffadc1387827"
)


def get_trusted_public_key() -> str:
    """Resolve the active trusted Ed25519 public key in priority order."""
    # 1. Environment variable override
    env_key = os.environ.get("UPDATER_PUBLIC_KEY", "").strip()
    if env_key:
        return env_key

    # 2. Django settings override if available
    try:
        from django.conf import settings
        cfg_key = getattr(settings, "UPDATER_PUBLIC_KEY", "").strip()
        if cfg_key:
            return cfg_key
    except Exception:
        pass

    # 3. Default embedded public key
    return DEFAULT_UPDATER_PUBLIC_KEY


def compute_sha256(target: Union[str, Path, bytes]) -> str:
    """Compute SHA-256 hex digest for a file path or in-memory bytes."""
    h = hashlib.sha256()
    if isinstance(target, (str, Path)):
        p = Path(target)
        if not p.is_file():
            raise FileNotFoundError(f"File not found for checksum: {target}")
        with open(p, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
    elif isinstance(target, bytes):
        h.update(target)
    else:
        raise TypeError("Target must be a Path, filename str, or bytes")
    return h.hexdigest().lower()


def verify_file_hash(target_path: Union[str, Path], expected_sha256: str) -> bool:
    """Verify that file's SHA-256 matches expected hex digest (case-insensitive)."""
    if not expected_sha256:
        return False
    computed = compute_sha256(target_path)
    return computed == expected_sha256.strip().lower()


def verify_signature(
    data: bytes,
    signature_hex: str,
    public_key_hex: str | None = None
) -> bool:
    """
    Verify Ed25519 signature over binary data using trusted public key.
    Returns True if signature is cryptographically valid, False otherwise.
    """
    if not signature_hex:
        return False

    pk_hex = (public_key_hex or get_trusted_public_key()).strip()
    if not pk_hex:
        return False

    try:
        sig_bytes = bytes.fromhex(signature_hex.strip())
        pk_bytes = bytes.fromhex(pk_hex)
    except ValueError:
        return False

    if len(sig_bytes) != 64 or len(pk_bytes) != 32:
        return False

    # 1. Try cryptography library if installed
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.exceptions import InvalidSignature
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(pk_bytes)
        try:
            public_key.verify(sig_bytes, data)
            return True
        except InvalidSignature:
            return False
    except ImportError:
        pass

    # 2. Use pure-Python RFC 8032 fallback
    from .ed25519_pure import ed25519_verify
    return ed25519_verify(pk_bytes, data, sig_bytes)


def sign_data(data: bytes, private_key_hex: str) -> str:
    """
    Sign binary data using Ed25519 private key seed (32 bytes / 64 hex chars).
    Used by release creation tools and test suites.
    """
    sk_bytes = bytes.fromhex(private_key_hex.strip())
    if len(sk_bytes) != 32:
        raise ValueError("Private key seed must be exactly 32 bytes (64 hex characters)")

    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(sk_bytes)
        sig = private_key.sign(data)
        return sig.hex()
    except ImportError:
        pass

    from .ed25519_pure import ed25519_sign
    return ed25519_sign(sk_bytes, data).hex()
