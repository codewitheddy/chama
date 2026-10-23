"""
Pure Python Ed25519 implementation adhering to RFC 8032.
=========================================================
Zero external dependencies (uses standard library `hashlib` only).
Provides cryptographic signature verification and key management
across Windows, Linux, and macOS without requiring binary C wheels.
"""

import hashlib
import os

# ── RFC 8032 Curve Constants (Edwards25519) ──────────────────────────────────
b = 256
q = 2**255 - 19
l = 2**252 + 27742317777372353535851937790883648493


def _H(m: bytes) -> bytes:
    return hashlib.sha512(m).digest()


def _expmod(b_val, e_val, m_val):
    return pow(b_val, e_val, m_val)


def _inv(x):
    return _expmod(x, q - 2, q)


d = -121665 * _inv(121666)
I = _expmod(2, (q - 1) // 4, q)


def _xrecover(y):
    xx = (y * y - 1) * _inv(d * y * y + 1)
    x = _expmod(xx, (q + 3) // 8, q)
    if (x * x - xx) % q != 0:
        x = (x * I) % q
    if x % 2 != 0:
        x = q - x
    return x


By = 4 * _inv(5)
Bx = _xrecover(By)
B = [Bx % q, By % q]


def _edwards_add(P, Q):
    x1, y1 = P
    x2, y2 = Q
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + d * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - d * x1 * x2 * y1 * y2)
    return [x3 % q, y3 % q]


def _scalarmult(P, e_val):
    if e_val == 0:
        return [0, 1]
    Q = _scalarmult(P, e_val // 2)
    Q = _edwards_add(Q, Q)
    if e_val & 1:
        Q = _edwards_add(Q, P)
    return Q


def _encodeint(y):
    return y.to_bytes(32, byteorder='little')


def _decodeint(s):
    return int.from_bytes(s, byteorder='little')


def _encodepoint(P):
    x = P[0]
    y = P[1]
    bits = [(y >> i) & 1 for i in range(b - 1)] + [x & 1]
    return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(b // 8))


def _decodepoint(s):
    if len(s) != 32:
        raise ValueError("Invalid point length")
    y = sum(s[i] << (i * 8) for i in range(b // 8))
    clamp_y = y & ((1 << 255) - 1)
    sign = (s[31] >> 7) & 1
    x = _xrecover(clamp_y)
    if bool(x & 1) != bool(sign):
        x = q - x
    P = [x, clamp_y]
    if not _isoncurve(P):
        raise ValueError("Point is not on curve")
    return P


def _isoncurve(P):
    x, y = P
    return (-x * x + y * y - 1 - d * x * x * y * y) % q == 0


# ── Public API ───────────────────────────────────────────────────────────────

def publickey_from_secret(sk: bytes) -> bytes:
    """Derive 32-byte public key from 32-byte private seed."""
    if len(sk) != 32:
        raise ValueError("Secret seed must be exactly 32 bytes")
    h = _H(sk)
    a = int.from_bytes(h[:32], byteorder='little')
    a &= (1 << 254) - 8
    a |= (1 << 254)
    A = _scalarmult(B, a)
    return _encodepoint(A)


def ed25519_sign(sk: bytes, m: bytes) -> bytes:
    """Sign message m using 32-byte secret seed sk. Returns 64-byte signature."""
    if len(sk) != 32:
        raise ValueError("Secret seed must be exactly 32 bytes")
    pk = publickey_from_secret(sk)
    h = _H(sk)
    a = int.from_bytes(h[:32], byteorder='little')
    a &= (1 << 254) - 8
    a |= (1 << 254)
    r = int.from_bytes(_H(h[32:] + m), byteorder='little') % l
    R = _scalarmult(B, r)
    R_enc = _encodepoint(R)
    k = int.from_bytes(_H(R_enc + pk + m), byteorder='little') % l
    S = (r + k * a) % l
    return R_enc + _encodeint(S)


def ed25519_verify(pk: bytes, m: bytes, sig: bytes) -> bool:
    """Verify 64-byte signature over message m using 32-byte public key pk."""
    if len(pk) != 32 or len(sig) != 64:
        return False
    try:
        R_bytes = sig[:32]
        S_bytes = sig[32:]
        S = _decodeint(S_bytes)
        if S >= l:
            return False
        A = _decodepoint(pk)
        R = _decodepoint(R_bytes)
        k = int.from_bytes(_H(R_bytes + pk + m), byteorder='little') % l
        SB = _scalarmult(B, S)
        kA = _scalarmult(A, k)
        RkA = _edwards_add(R, kA)
        return SB == RkA
    except Exception:
        return False


def generate_keypair() -> tuple[str, str]:
    """Generate a new random Ed25519 keypair. Returns (private_hex, public_hex)."""
    sk = os.urandom(32)
    pk = publickey_from_secret(sk)
    return sk.hex(), pk.hex()
