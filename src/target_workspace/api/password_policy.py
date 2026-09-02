"""Password policy validator (tw-fn7a).

NIST SP 800-63B-aligned defaults. CJIS / FedRAMP environments tighten
via env vars (TW_PASSWORD_*).
"""

from __future__ import annotations

from fastapi import HTTPException, status

from target_workspace.api.config import Settings

SPECIAL_CHARS = set("!@#$%^&*()_+-=[]{}|;:,.<>?/'\"\\`~")


def validate_password(password: str, settings: Settings) -> None:
    """Raise HTTPException(422) if the password violates the policy.

    Returns None on success. Callers wire this into every password-
    setting endpoint.
    """
    problems: list[str] = []
    if len(password) < settings.password_min_length:
        problems.append(
            f"password must be at least {settings.password_min_length} characters",
        )
    if settings.password_require_mixed_case and not (
        any(c.isupper() for c in password) and any(c.islower() for c in password)
    ):
        problems.append("password must include both uppercase and lowercase letters")
    if settings.password_require_digit and not any(c.isdigit() for c in password):
        problems.append("password must include a digit")
    if settings.password_require_special and not any(c in SPECIAL_CHARS for c in password):
        problems.append("password must include a special character")
    if problems:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="password rejected: " + "; ".join(problems),
        )
