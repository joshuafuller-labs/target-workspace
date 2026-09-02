"""POST /v1/capture — mobile-friendly target capture (tw-bux).

Multipart endpoint. Wraps the standard target-creation path (so audit,
realtime, RBAC, correlation all work uniformly) with a thin upload
shim for an optional photo.

Photo storage at MVP: write to settings.captures_dir (or fallback temp
dir) as <target_id>.bin, with the absolute path recorded on
target.custom_fields['photo_path']. Pre-signed URL pattern (S3 / MinIO)
is deferred to v1.1.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlmodel import Session

from target_workspace.api.config import Settings, get_settings
from target_workspace.api.dependencies import current_user, db_session
from target_workspace.api.schemas import TargetCreate
from target_workspace.db.tables import UserTable
from target_workspace.models.target import Target

router = APIRouter(prefix="/v1/capture", tags=["capture"])


def _resolve_captures_dir(settings: Settings) -> Path:
    if settings.captures_dir:
        p = Path(settings.captures_dir)
    elif os.environ.get("XDG_DATA_HOME"):
        p = Path(os.environ["XDG_DATA_HOME"]) / "tw" / "captures"
    else:
        p = Path("/tmp") / "tw-captures"  # noqa: S108
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.post("", response_model=Target, status_code=status.HTTP_201_CREATED)
def capture(
    request: Request,
    title: str = Form(min_length=1, max_length=200),
    lat: float = Form(ge=-90.0, le=90.0),
    lon: float = Form(ge=-180.0, le=180.0),
    board_id: UUID = Form(...),
    column_id: UUID = Form(...),
    cot_type: str = Form(default="a-u-G", min_length=1),
    remarks: str | None = Form(default=None, max_length=4000),
    photo: UploadFile | None = File(default=None),
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> Target:
    # Delegate to the standard target-creation flow so audit + realtime
    # + RBAC + correlation behave identically to manual creation.
    from target_workspace.api.routers.targets import create_target  # noqa: PLC0415

    custom_fields: dict[str, Any] = {}

    if photo is not None and photo.filename:
        # Save the upload bytes first; we don't have a target_id yet so
        # write to a temp location, then rename once we know it.
        captures_dir = _resolve_captures_dir(settings)
        body_bytes = photo.file.read()
        if not body_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="photo upload was empty",
            )
        # Write to a stable name later — for now hold in memory + path.
        custom_fields["_pending_photo_bytes_b64"] = None  # sentinel; populated below

    target_create = TargetCreate(
        board_id=board_id,
        column_id=column_id,
        name=title,
        cot_type=cot_type,
        lat=lat,
        lon=lon,
        time=datetime.now(tz=UTC),
        remarks=remarks,
        custom_fields={},
    )

    created = create_target(body=target_create, request=request, session=session, user=user)

    if photo is not None and photo.filename:
        captures_dir = _resolve_captures_dir(settings)
        out_path = captures_dir / f"{created.id}.bin"
        out_path.write_bytes(body_bytes)
        # Patch the target with the recorded path. Use the SQL row directly
        # to avoid going through the PATCH endpoint dependency chain.
        from target_workspace.db.tables import TargetTable  # noqa: PLC0415

        row = session.get(TargetTable, created.id)
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="created target disappeared",
            )
        new_custom = dict(row.custom_fields or {})
        new_custom["photo_path"] = str(out_path)
        row.custom_fields = new_custom
        session.add(row)
        session.flush()
        # Re-fetch as the response model
        from target_workspace.db import repositories as repo  # noqa: PLC0415

        refreshed = repo.get_target(session, created.id)
        if refreshed is not None:
            return refreshed
    return created
