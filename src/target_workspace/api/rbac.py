"""Role-based access control — tiered access per the Ukraine audit.

Delta's tiered access pattern (battalion → brigade → division gets
different read/write/approve permissions) maps to a small ordered set of
roles. We use 6 tiers; each implies the privileges of every lower tier.

Hierarchy (lowest → highest):

  viewer     read-only access to boards / targets / audit
  observer   + create targets (raw observation submission)
  operator   + edit + move targets (the workflow user)
  approver   + satisfy approval-gated column transitions
  commander  + delete + create/destroy boards
  admin      full access including user management

Per docs/research/ukraine-fires-targeting.md §1 ("Tiered RBAC"). The
default seeded admin user retains full access — this is purely additive
authorization on top of the cookie-session auth that's been in place
since the MVP.

Unknown role strings → "viewer" (least-privilege fallback). New users
who haven't been provisioned a tier can still see, but not write.
"""

from __future__ import annotations

from typing import Final

from fastapi import HTTPException, status

# Ordered tier list; index = privilege level. Lower index = lower trust.
_TIERS: Final[tuple[str, ...]] = (
    "viewer",
    "observer",
    "operator",
    "approver",
    "commander",
    "admin",
)
_TIER_INDEX: Final[dict[str, int]] = {r: i for i, r in enumerate(_TIERS)}


def role_rank(role: str) -> int:
    """Privilege rank for `role`. Unknown roles fall back to `viewer`."""
    return _TIER_INDEX.get(role, 0)


def has_role(user_role: str, required: str) -> bool:
    """True iff user_role's tier is >= required tier."""
    return role_rank(user_role) >= role_rank(required)


def require_role(user_role: str, required: str, *, action: str) -> None:
    """Raise 403 HTTPException if `user_role` is below `required`.

    `action` is a short verb describing what's being attempted; lands in
    the error detail so denied users see *why* it was denied, not just
    "forbidden".
    """
    if has_role(user_role, required):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            f"{action} requires role '{required}' or higher; "
            f"your role '{user_role}' is insufficient"
        ),
    )
