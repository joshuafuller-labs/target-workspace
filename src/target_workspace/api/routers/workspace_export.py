"""Workspace export / import endpoints (tw-b0ky).

POST /v1/workspace/export → tar.gz download (admin only).
POST /v1/workspace/import → restore from tar.gz (admin only, refuses if
populated).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from target_workspace.api.config import Settings, get_settings
from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.api.rbac import require_role
from target_workspace.api.snapshot import (
    current_schema_version,
    make_snapshot,
)
from target_workspace.db.tables import UserTable

router = APIRouter(prefix="/v1/workspace", tags=["workspace"])


def _db_file_path(settings: Settings) -> str:
    """Extract the sqlite file path from settings.database_url (sqlite:///...)."""
    url = settings.database_url
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///") :]
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="workspace export only supports sqlite backends at MVP",
    )


@router.get("/setup-status")
def setup_status(
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("workspace:read")),
) -> dict[str, Any]:
    """First-run detection for the setup wizard. tw-1csv.

    Returns whether the wizard should prompt the admin to onboard:
      - is_first_run: True when zero boards exist
      - board_count
      - workspace_name (so the SPA can show 'still named Default' nudges)
    """
    from sqlmodel import select  # noqa: PLC0415

    from target_workspace.db.tables import BoardTable, WorkspaceTable  # noqa: PLC0415

    ws = session.exec(
        select(WorkspaceTable).where(WorkspaceTable.id == user.workspace_id),
    ).first()
    boards = session.exec(
        select(BoardTable).where(BoardTable.workspace_id == user.workspace_id),
    ).all()
    return {
        "is_first_run": len(boards) == 0,
        "board_count": len(boards),
        "workspace_name": ws.name if ws else "",
    }


class _WorkspacePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)


@router.patch("")
def patch_workspace(
    body: _WorkspacePatch,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("workspace:write")),
) -> dict[str, Any]:
    """Rename the workspace. Admin-only. tw-1csv."""
    require_role(user.role, "admin", action="rename workspace")
    from target_workspace.db.tables import WorkspaceTable  # noqa: PLC0415

    ws = session.get(WorkspaceTable, user.workspace_id)
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")
    ws.name = body.name
    session.add(ws)
    session.flush()
    return {"id": str(ws.id), "name": ws.name}


@router.get("/demo-scenarios")
def demo_scenarios(
    user: UserTable = Depends(require_token_scope("workspace:read")),
) -> list[dict[str, Any]]:
    """List bundled demo scenarios the SPA can load as empty-state actions.

    tw-jxl: enables 'load demo scenario' button on the no-boards-yet
    screen.
    """
    from target_workspace.demo.loader import discover_scenarios  # noqa: PLC0415

    found = discover_scenarios()
    return [{"id": sid, "name": scn.name} for sid, scn in sorted(found.items())]


@router.get("/map-config")
def map_config(
    settings: Settings = Depends(get_settings),
    user: UserTable = Depends(require_token_scope("workspace:read")),
) -> dict[str, str]:
    """Return the workspace map tile configuration. tw-45s.

    When `settings.map_tile_url` is empty, the frontend uses its bundled
    Natural Earth tile pyramid. Otherwise the URL is used directly as
    a Cesium UrlTemplateImageryProvider.
    """
    url = settings.map_tile_url or ""
    return {
        "tile_url": url,
        "provider": "override" if url else "bundled-natural-earth",
    }


@router.post("/export")
def export_workspace(
    user: UserTable = Depends(require_token_scope("workspace:export")),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Return a tar.gz snapshot of the workspace database. Admin only."""
    require_role(user.role, "admin", action="export workspace")
    db_path = _db_file_path(settings)
    manifest = {
        "version": "1",
        "schema_version": current_schema_version(db_path),
        "exported_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "exporter_user_id": str(user.id),
    }
    payload = make_snapshot(src_db_path=db_path, manifest=manifest)
    filename = f"workspace-snapshot-{datetime.now(tz=UTC).strftime('%Y%m%d-%H%M%S')}.tar.gz"
    return Response(
        content=payload,
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
