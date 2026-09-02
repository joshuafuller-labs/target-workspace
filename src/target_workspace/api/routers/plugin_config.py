"""/v1/plugins, /v1/sources, /v1/publishers admin config API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from target_workspace.api.auth_audit import emit_auth_event
from target_workspace.api.dependencies import (
    current_user,
    db_session,
    enforce_token_scope,
    require_token_scope,
)
from target_workspace.api.rbac import require_role
from target_workspace.db.tables import PublisherConfigTable, SourceConfigTable, UserTable
from target_workspace.plugins.loader import (
    discover_effectors,
    discover_publishers,
    discover_sources,
    register_builtin_plugins,
)

plugins_router = APIRouter(prefix="/v1/plugins", tags=["plugins"])
sources_router = APIRouter(prefix="/v1/sources", tags=["sources"])
publishers_router = APIRouter(prefix="/v1/publishers", tags=["publishers"])


class PluginInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    kind: str


class PluginCatalogOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: list[PluginInfo]
    publishers: list[PluginInfo]
    effectors: list[PluginInfo]


class SourceConfigCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    plugin_type: str = Field(min_length=1, max_length=80)
    enabled: bool = True
    adapter_config: dict[str, Any] = Field(default_factory=dict)
    normalization_map: dict[str, Any] = Field(default_factory=dict)
    promotion_policy_id: UUID | None = None


class SourceConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    plugin_type: str | None = Field(default=None, min_length=1, max_length=80)
    enabled: bool | None = None
    adapter_config: dict[str, Any] | None = None
    normalization_map: dict[str, Any] | None = None
    promotion_policy_id: UUID | None = None


class SourceConfigOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    plugin_type: str
    enabled: bool
    adapter_config: dict[str, Any]
    normalization_map: dict[str, Any]
    promotion_policy_id: UUID | None


class SourceTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: dict[str, Any] = Field(default_factory=dict)


class SourceTestOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    normalized: dict[str, Any]


class PublisherConfigCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    plugin_type: str = Field(min_length=1, max_length=80)
    enabled: bool = True
    adapter_config: dict[str, Any] = Field(default_factory=dict)
    column_filter_ids: list[UUID] = Field(default_factory=list)


class PublisherConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    plugin_type: str | None = Field(default=None, min_length=1, max_length=80)
    enabled: bool | None = None
    adapter_config: dict[str, Any] | None = None
    column_filter_ids: list[UUID] | None = None


class PublisherConfigOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    plugin_type: str
    enabled: bool
    adapter_config: dict[str, Any]
    column_filter_ids: list[UUID]


def _admin(user: UserTable, *, action: str) -> None:
    require_role(user.role, "admin", action=action)


def _plugin_items(names: list[str], kind: str) -> list[dict[str, str]]:
    return [{"name": name, "kind": kind} for name in sorted(names)]


def _source_out(row: SourceConfigTable) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "plugin_type": row.plugin_type,
        "enabled": row.enabled,
        "adapter_config": dict(row.adapter_config or {}),
        "normalization_map": dict(row.normalization_map or {}),
        "promotion_policy_id": row.promotion_policy_id,
    }


def _publisher_out(row: PublisherConfigTable) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "plugin_type": row.plugin_type,
        "enabled": row.enabled,
        "adapter_config": dict(row.adapter_config or {}),
        "column_filter_ids": [UUID(str(value)) for value in row.column_filter_ids or []],
    }


def _require_source_plugin(plugin_type: str) -> type[Any]:
    register_builtin_plugins()
    plugins = discover_sources()
    if plugin_type not in plugins:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown source plugin_type: {plugin_type}",
        )
    return plugins[plugin_type]


def _require_publisher_plugin(plugin_type: str) -> None:
    register_builtin_plugins()
    if plugin_type not in discover_publishers():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown publisher plugin_type: {plugin_type}",
        )


def _emit_config_event(
    session: Session,
    *,
    user: UserTable,
    event_type: str,
    metadata: dict[str, Any],
) -> None:
    emit_auth_event(
        session,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event_type=event_type,
        metadata=metadata,
    )


@plugins_router.get("", response_model=PluginCatalogOut)
def list_plugins(
    user: UserTable = Depends(require_token_scope("plugins:read")),
) -> dict[str, Any]:
    _admin(user, action="list plugins")
    register_builtin_plugins()
    return {
        "sources": _plugin_items(list(discover_sources()), "source"),
        "publishers": _plugin_items(list(discover_publishers()), "publisher"),
        "effectors": _plugin_items(list(discover_effectors()), "effector"),
    }


@sources_router.get("", response_model=list[SourceConfigOut])
def list_sources(
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("sources:read")),
) -> list[dict[str, Any]]:
    _admin(user, action="list sources")
    rows = session.exec(
        select(SourceConfigTable).where(SourceConfigTable.workspace_id == user.workspace_id),
    ).all()
    return [_source_out(row) for row in rows]


@sources_router.post("", response_model=SourceConfigOut, status_code=status.HTTP_201_CREATED)
def create_source(
    body: SourceConfigCreate,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> dict[str, Any]:
    enforce_token_scope(request, "sources:write", f"sources:write:plugin:{body.plugin_type}")
    _admin(user, action="create sources")
    _require_source_plugin(body.plugin_type)
    row = SourceConfigTable(
        workspace_id=user.workspace_id,
        name=body.name,
        plugin_type=body.plugin_type,
        enabled=body.enabled,
        adapter_config=dict(body.adapter_config),
        normalization_map=dict(body.normalization_map),
        promotion_policy_id=body.promotion_policy_id,
    )
    session.add(row)
    session.flush()
    _emit_config_event(
        session,
        user=user,
        event_type="source.created",
        metadata={"source_config_id": str(row.id), "plugin_type": row.plugin_type},
    )
    return _source_out(row)


@sources_router.patch("/{source_id}", response_model=SourceConfigOut)
def update_source(
    source_id: UUID,
    body: SourceConfigPatch,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> dict[str, Any]:
    row = session.get(SourceConfigTable, source_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")
    enforce_token_scope(request, "sources:write", f"sources:write:plugin:{row.plugin_type}")
    _admin(user, action="update sources")
    updates = body.model_dump(exclude_unset=True)
    if "plugin_type" in updates:
        _require_source_plugin(updates["plugin_type"])
        enforce_token_scope(
            request,
            "sources:write",
            f"sources:write:plugin:{updates['plugin_type']}",
        )
    for key, value in updates.items():
        setattr(row, key, value)
    session.add(row)
    session.flush()
    _emit_config_event(
        session,
        user=user,
        event_type="source.updated",
        metadata={
            "source_config_id": str(row.id),
            "plugin_type": row.plugin_type,
            "changed_fields": sorted(updates),
        },
    )
    return _source_out(row)


@sources_router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    source_id: UUID,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> Response:
    row = session.get(SourceConfigTable, source_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")
    enforce_token_scope(request, "sources:write", f"sources:write:plugin:{row.plugin_type}")
    _admin(user, action="delete sources")
    plugin_type = row.plugin_type
    session.delete(row)
    _emit_config_event(
        session,
        user=user,
        event_type="source.deleted",
        metadata={"source_config_id": str(source_id), "plugin_type": plugin_type},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@sources_router.post("/{source_id}/test", response_model=SourceTestOut)
def probe_source_config(
    source_id: UUID,
    body: SourceTestRequest,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> dict[str, Any]:
    row = session.get(SourceConfigTable, source_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="source not found")
    enforce_token_scope(request, "sources:write", f"sources:write:plugin:{row.plugin_type}")
    _admin(user, action="test sources")
    cls = _require_source_plugin(row.plugin_type)
    try:
        normalized = cls().normalize(
            body.payload,
            dict(row.normalization_map or {}),
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return {"normalized": normalized}


@publishers_router.get("", response_model=list[PublisherConfigOut])
def list_publishers(
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("publishers:read")),
) -> list[dict[str, Any]]:
    _admin(user, action="list publishers")
    rows = session.exec(
        select(PublisherConfigTable).where(PublisherConfigTable.workspace_id == user.workspace_id),
    ).all()
    return [_publisher_out(row) for row in rows]


@publishers_router.post("", response_model=PublisherConfigOut, status_code=status.HTTP_201_CREATED)
def create_publisher(
    body: PublisherConfigCreate,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> dict[str, Any]:
    enforce_token_scope(
        request,
        "publishers:write",
        f"publishers:write:plugin:{body.plugin_type}",
    )
    _admin(user, action="create publishers")
    _require_publisher_plugin(body.plugin_type)
    row = PublisherConfigTable(
        workspace_id=user.workspace_id,
        name=body.name,
        plugin_type=body.plugin_type,
        enabled=body.enabled,
        adapter_config=dict(body.adapter_config),
        column_filter_ids=[str(value) for value in body.column_filter_ids],
    )
    session.add(row)
    session.flush()
    _emit_config_event(
        session,
        user=user,
        event_type="publisher.created",
        metadata={"publisher_config_id": str(row.id), "plugin_type": row.plugin_type},
    )
    return _publisher_out(row)


@publishers_router.patch("/{publisher_id}", response_model=PublisherConfigOut)
def update_publisher(
    publisher_id: UUID,
    body: PublisherConfigPatch,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> dict[str, Any]:
    row = session.get(PublisherConfigTable, publisher_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="publisher not found")
    enforce_token_scope(request, "publishers:write", f"publishers:write:plugin:{row.plugin_type}")
    _admin(user, action="update publishers")
    updates = body.model_dump(exclude_unset=True)
    if "plugin_type" in updates:
        _require_publisher_plugin(updates["plugin_type"])
        enforce_token_scope(
            request,
            "publishers:write",
            f"publishers:write:plugin:{updates['plugin_type']}",
        )
    if "column_filter_ids" in updates:
        updates["column_filter_ids"] = [str(value) for value in updates["column_filter_ids"]]
    for key, value in updates.items():
        setattr(row, key, value)
    session.add(row)
    session.flush()
    _emit_config_event(
        session,
        user=user,
        event_type="publisher.updated",
        metadata={
            "publisher_config_id": str(row.id),
            "plugin_type": row.plugin_type,
            "changed_fields": sorted(updates),
        },
    )
    return _publisher_out(row)


@publishers_router.delete("/{publisher_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_publisher(
    publisher_id: UUID,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> Response:
    row = session.get(PublisherConfigTable, publisher_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="publisher not found")
    enforce_token_scope(request, "publishers:write", f"publishers:write:plugin:{row.plugin_type}")
    _admin(user, action="delete publishers")
    plugin_type = row.plugin_type
    session.delete(row)
    _emit_config_event(
        session,
        user=user,
        event_type="publisher.deleted",
        metadata={"publisher_config_id": str(publisher_id), "plugin_type": plugin_type},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
