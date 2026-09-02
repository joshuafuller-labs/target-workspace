"""/v1/ingest — HTTP webhook Source endpoint (tw-h7x).

External systems POST a per-source body here with a bearer token.
Server looks up the SourceConfig, verifies the token, applies the
configured normalization_map (via HttpWebhookSource), and creates one
or more Targets.

This is the 'we can ingest from any AI/CV/OSINT pipeline' MVP gap
closer. Per-source config (token + field map + target board/column)
lives in SourceConfigTable. Source config CRUD UI is a separate bd
(tw-dpe8); for now operators seed via DB / scenario.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlmodel import Session

from target_workspace.api.auth import verify_password
from target_workspace.api.dependencies import db_session
from target_workspace.api.realtime import get_broker, make_event
from target_workspace.db import repositories as repo
from target_workspace.db.tables import SourceConfigTable
from target_workspace.models.target import Target
from target_workspace.plugins.sources.http_webhook import HttpWebhookSource

router = APIRouter(prefix="/v1/ingest", tags=["ingest"])

_webhook = HttpWebhookSource()


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":  # noqa: PLR2004 — Authorization header is exactly "Bearer <token>"
        return None
    return parts[1].strip()


@router.post("/{source_id}", status_code=status.HTTP_201_CREATED)
async def ingest_webhook(
    source_id: UUID,
    request: Request,
    session: Session = Depends(db_session),
    authorization: str | None = Header(default=None),
) -> Any:
    """Webhook endpoint for external Source adapters.

    Body: a single JSON object OR an array of objects (bulk).
    Auth: Bearer token matching the SourceConfig's stored hash.
    Response: created Target (or list of Targets for bulk), 201.
    """
    src = session.get(SourceConfigTable, source_id)
    if src is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="source not found",
        )

    token = _extract_bearer(authorization)
    expected_hash = src.adapter_config.get("token_hash") if src.adapter_config else None
    if not token or not expected_hash or not verify_password(token, expected_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not src.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="source is disabled",
        )

    board_id = src.adapter_config.get("board_id")
    column_id = src.adapter_config.get("column_id")
    if not board_id or not column_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="source missing board_id / column_id in adapter_config",
        )

    body = await request.json()
    items = body if isinstance(body, list) else [body]

    results: list[Target] = []
    for raw in items:
        if not isinstance(raw, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="each item must be a JSON object",
            )
        try:
            normalized = _webhook.normalize(raw, src.normalization_map or {})
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc).strip("'\""),
            ) from exc

        # Build a Target from the normalized dict. Pydantic validates
        # required fields (name, lat, lon, time) and types — missing
        # values surface as a 422 with field-level detail.
        try:
            target = Target(**normalized)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"normalized payload failed validation: {exc}",
            ) from exc

        repo.create_target(
            session,
            src.workspace_id,
            UUID(board_id),
            UUID(column_id),
            target,
        )
        get_broker().publish(
            src.workspace_id,
            make_event(
                event_type="target.created",
                workspace_id=src.workspace_id,
                board_id=UUID(board_id),
                target_id=target.id,
                occurred_at=datetime.now(tz=UTC).isoformat(),
                data={
                    "source_id": str(source_id),
                    "name": target.name,
                    "via": "webhook",
                },
            ),
        )
        results.append(target)

    # Single object in → single object out; array in → array out.
    return results if isinstance(body, list) else results[0]


# Side-effect — register the source at module import.
_ = uuid4  # keep the import non-dead in case unused elsewhere
