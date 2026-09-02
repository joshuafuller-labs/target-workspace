"""RFC 6238 TOTP — stdlib implementation (tw-mg1a).

No new dependency. Uses Python's hmac/hashlib + base64. 30-second
timestep, 6-digit codes, SHA1 (per RFC 6238 default; matches
Google Authenticator / Authy / 1Password).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

DIGITS = 6
TIMESTEP_SECONDS = 30


def generate_secret() -> str:
    """Return a base32-encoded 20-byte secret suitable for TOTP enrollment."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int) -> str:
    # Pad to a multiple of 8 for base32
    padded = secret_b32 + "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(padded.upper())
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**DIGITS)
    return str(code_int).zfill(DIGITS)


def generate_code(secret_b32: str, now: float | None = None) -> str:
    """Current code for the secret. Pass `now` (UNIX timestamp) for tests."""
    t = now if now is not None else time.time()
    counter = int(t // TIMESTEP_SECONDS)
    return _hotp(secret_b32, counter)


def verify_code(
    secret_b32: str,
    code: str,
    *,
    window: int = 1,
    now: float | None = None,
) -> bool:
    """Constant-time verify within +/- `window` timesteps."""
    if not code or not code.isdigit():
        return False
    t = now if now is not None else time.time()
    counter = int(t // TIMESTEP_SECONDS)
    for delta in range(-window, window + 1):
        expected = _hotp(secret_b32, counter + delta)
        if hmac.compare_digest(expected, code):
            return True
    return False


def provisioning_uri(
    *,
    secret_b32: str,
    account_name: str,
    issuer: str = "Target Workspace",
) -> str:
    """otpauth:// URI for QR-code rendering. Standard format consumed by
    Google Authenticator / Authy / 1Password."""
    label = quote(f"{issuer}:{account_name}")
    params = (
        f"secret={secret_b32}"
        f"&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={DIGITS}&period={TIMESTEP_SECONDS}"
    )
    return f"otpauth://totp/{label}?{params}"
