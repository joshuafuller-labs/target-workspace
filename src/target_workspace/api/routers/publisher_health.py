"""/v1/publishers/health — per-publisher telemetry (tw-mowp)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from target_workspace.api.dependencies import require_token_scope
from target_workspace.api.publisher_health import snapshot
from target_workspace.db.tables import UserTable

router = APIRouter(prefix="/v1/publishers", tags=["publishers"])


@router.get("/health")
def publisher_health(
    user: UserTable = Depends(require_token_scope("publishers:read")),
) -> list[dict[str, Any]]:
    return snapshot()
