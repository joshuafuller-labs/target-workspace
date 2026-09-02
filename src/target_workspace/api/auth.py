"""Session-cookie auth for MVP.

Single admin, bcrypt-hashed password, signed cookie. The auth seam is
pluggable per ADR 0013 — bearer-JWT for mobile/plugin clients and
client-credentials for ATAK plugin land in subsequent commits.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from uuid import UUID

import bcrypt

DEFAULT_BCRYPT_ROUNDS = 12
MIN_TEST_BCRYPT_ROUNDS = 4


def bcrypt_rounds_for_env(*, env: str, requested_rounds: int) -> int:
    """Resolve bcrypt cost.

    Tests may lower bcrypt cost because repeated app boot/login dominates
    wall-clock runtime. Non-test environments clamp to the production floor.
    """
    if env == "test":
        return max(MIN_TEST_BCRYPT_ROUNDS, requested_rounds)
    return max(DEFAULT_BCRYPT_ROUNDS, requested_rounds)


def hash_password(
    plaintext: str,
    *,
    env: str | None = None,
    bcrypt_rounds: int | None = None,
) -> str:
    """bcrypt hash. Stored in users.password_hash."""
    if env is None or bcrypt_rounds is None:
        from target_workspace.api.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        env = settings.env if env is None else env
        bcrypt_rounds = settings.bcrypt_rounds if bcrypt_rounds is None else bcrypt_rounds
    rounds = bcrypt_rounds_for_env(env=env, requested_rounds=bcrypt_rounds)
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    """Constant-time bcrypt verify."""
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def sign_session(user_id: UUID, secret: str, *, session_version: int = 0) -> str:
    """Produce a signed session token for a user_id.

    Format: base64url(payload).base64url(hmac-sha256(payload, secret))
    Payload carries the uid plus a session_version (tw-ptn2) that lets
    the server invalidate every existing cookie for a user by bumping
    the version on the user row.
    """
    payload = json.dumps(
        {"uid": str(user_id), "sv": session_version},
        separators=(",", ":"),
    ).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return f"{urlsafe_b64encode(payload).decode()}.{urlsafe_b64encode(sig).decode()}"


def verify_session(token: str, secret: str) -> UUID | None:
    """Verify a session token and return the user_id, or None if invalid.

    Note: returns the uid only; the session_version is checked by
    dependencies.current_user against the live user row.
    """
    parsed = verify_session_full(token, secret)
    return parsed[0] if parsed is not None else None


def verify_session_full(token: str, secret: str) -> tuple[UUID, int] | None:
    """Verify and return (uid, session_version) — None on failure."""
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = urlsafe_b64decode(payload_b64)
        sig = urlsafe_b64decode(sig_b64)
    except (ValueError, AttributeError):
        return None
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(payload)
        return UUID(data["uid"]), int(data.get("sv", 0))
    except (json.JSONDecodeError, KeyError, ValueError):
        return None
