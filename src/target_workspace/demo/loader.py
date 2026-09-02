"""Load and apply scenario YAML files.

Scenario shape (YAML):

    name: "TF DAGGER F3EAD"
    workspace_name: "TF DAGGER"
    board:
      name: "F3EAD"
      transitions: unrestricted
      columns:
        - { name: FIND,   order: 0 }
        - { name: FIX,    order: 1 }
        - { name: FINISH, order: 2, requires_approval: true }
        ...
    publishers:
      - name: "raw CoT (multicast)"
        plugin_type: raw_cot
        adapter_config: { transport: udp, host: 239.2.3.1, port: 6969 }
        column_filter_names: [FINISH, DISSEM]
    targets:
      - name: BISON-01
        column_name: FIND
        cot_type: a-h-G-E-V
        lat: 33.4484
        lon: -112.0740
        confidence: 0.87
        minutes_ago: 7
        custom_fields:
          jiptl_priority: 4
          source: CV-ATR (MQ-9)
        transitions:                  # historical moves, oldest first
          - { to_column: FIX, justification: "cross-cue confirmed", minutes_ago: 6 }

Each target's `transitions` list is replayed in order with realistic
past-timestamps; the audit log captures them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from sqlalchemy import Engine
from sqlmodel import Session, select

from target_workspace.db.repositories import create_board, create_target, create_workspace
from target_workspace.db.tables import (
    AuditEventTable,
    BoardTable,
    PublisherConfigTable,
    UserTable,
    WorkspaceTable,
)
from target_workspace.models.board import Board, Column
from target_workspace.models.target import Target


class ScenarioNotFoundError(LookupError):
    pass


@dataclass
class Scenario:
    name: str
    raw: dict[str, Any]
    source_path: Path


def _bundled_dir() -> Path:
    """Where bundled scenario YAML files live."""
    return Path(__file__).resolve().parent / "scenarios"


def discover_scenarios() -> dict[str, Scenario]:
    """Return mapping of scenario id (file stem) -> Scenario."""
    result: dict[str, Scenario] = {}
    for path in sorted(_bundled_dir().glob("*.yaml")):
        with path.open() as fh:
            raw = yaml.safe_load(fh) or {}
        result[path.stem] = Scenario(
            name=str(raw.get("name", path.stem)), raw=raw, source_path=path
        )
    return result


def load_scenario(scenario_id: str) -> Scenario:
    found = discover_scenarios().get(scenario_id)
    if found is None:
        msg = f"scenario not found: {scenario_id!r} (available: {sorted(discover_scenarios())})"
        raise ScenarioNotFoundError(msg)
    return found


def _resolve_actor(session: Session) -> UUID:
    """Pick any admin (bootstrap user) to be the recorded actor."""
    actor = session.exec(select(UserTable).where(UserTable.role == "admin")).first()
    if actor is None:
        actor = session.exec(select(UserTable)).first()
    if actor is None:
        msg = "no users in DB — seed_workspace requires a bootstrapped admin"
        raise RuntimeError(msg)
    return actor.id


def _record_audit(
    session: Session,
    *,
    workspace_id: UUID,
    target_id: UUID,
    actor_id: UUID,
    event_type: str,
    occurred_at: datetime,
    from_column_id: UUID | None = None,
    to_column_id: UUID | None = None,
    justification: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append an audit row with an explicit past timestamp (replays don't use now())."""
    session.add(
        AuditEventTable(
            workspace_id=workspace_id,
            target_id=target_id,
            actor_id=actor_id,
            event_type=event_type,
            occurred_at=occurred_at,
            from_column_id=from_column_id,
            to_column_id=to_column_id,
            justification=justification,
            metadata_json=dict(metadata or {}),
        )
    )


def seed_workspace(  # noqa: PLR0915 — single orchestrator; refactor post-demo
    engine: Engine,
    *,
    scenario_id: str,
    now: datetime | None = None,
    workspace_id: UUID | None = None,
) -> dict[str, Any]:
    """Apply scenario `scenario_id`.

    By default seeds INTO the bootstrap admin's workspace (so login surfaces
    every seeded scenario's board). Pass `workspace_id` to target a specific
    workspace. Idempotent at the *board* level: if a board with the
    scenario's board name already exists in the target workspace, no-op.
    """
    scenario = load_scenario(scenario_id)
    raw = scenario.raw
    when_now = now or datetime.now(tz=UTC)

    with Session(engine) as session:
        session.expire_on_commit = False

        if workspace_id is not None:
            ws = session.get(WorkspaceTable, workspace_id)
            if ws is None:
                msg = f"workspace {workspace_id} not found"
                raise RuntimeError(msg)
        else:
            # Default: seed into whichever workspace the bootstrap admin owns.
            admin = session.exec(select(UserTable).where(UserTable.role == "admin")).first()
            if admin is None:
                # No admin yet — fall back to creating a brand-new workspace.
                ws = create_workspace(
                    session,
                    name=str(raw.get("workspace_name") or raw.get("name") or scenario_id),
                )
            else:
                ws = session.get(WorkspaceTable, admin.workspace_id)
                if ws is None:
                    msg = "admin's workspace missing"
                    raise RuntimeError(msg)

        board_name = str(raw["board"]["name"])
        existing_board = session.exec(
            select(BoardTable).where(
                BoardTable.workspace_id == ws.id,
                BoardTable.name == board_name,
            )
        ).first()
        if existing_board is not None:
            return {
                "status": "already-seeded",
                "scenario": scenario_id,
                "workspace_id": str(ws.id),
                "board_id": str(existing_board.id),
            }

        actor_id = _resolve_actor(session)

        # Board
        board_raw = raw["board"]
        board = Board(
            name=str(board_raw["name"]),
            transitions=str(board_raw.get("transitions", "unrestricted")),
            theme=str(board_raw.get("theme", "neutral")),
            columns=[
                Column(
                    name=str(c["name"]),
                    order=int(c["order"]),
                    wip_limit=c.get("wip_limit"),
                    color=c.get("color"),
                    requires_approval=bool(c.get("requires_approval", False)),
                )
                for c in board_raw["columns"]
            ],
        )
        create_board(session, ws.id, board)

        # Map column-name -> column.id for lookups in target + publisher blocks
        cols_by_name = {c.name: c for c in board.columns}

        # Publishers (optional)
        publishers_created: list[str] = []
        for p in raw.get("publishers") or []:
            filter_ids = [
                str(cols_by_name[n].id)
                for n in (p.get("column_filter_names") or [])
                if n in cols_by_name
            ]
            session.add(
                PublisherConfigTable(
                    workspace_id=ws.id,
                    name=str(p["name"]),
                    plugin_type=str(p["plugin_type"]),
                    enabled=bool(p.get("enabled", True)),
                    adapter_config=dict(p.get("adapter_config") or {}),
                    column_filter_ids=filter_ids,
                )
            )
            publishers_created.append(str(p["name"]))

        # Targets (with optional transition history)
        targets_created = 0
        transitions_replayed = 0
        for t in raw.get("targets") or []:
            initial_col = cols_by_name[str(t["column_name"])]
            minutes_ago = int(t.get("minutes_ago", 0))
            source_time = when_now - timedelta(minutes=minutes_ago)
            # Optional geometry beyond point + a quality tag (see ADR-aligned
            # docs/research/ukraine-fires-targeting.md §5).
            from target_workspace.models.target import Ellipse  # noqa: PLC0415

            geom_kind = str(t.get("geometry_kind", "point"))
            ellipse_raw = t.get("ellipse")
            ellipse_obj = Ellipse(**ellipse_raw) if ellipse_raw else None
            poly_vertices = t.get("polygon_vertices")
            geometry_quality = str(t.get("geometry_quality", "single-source"))
            target = Target(
                name=str(t["name"]),
                cot_type=str(t.get("cot_type", "a-u-G")),
                category=t.get("category"),
                lat=float(t["lat"]),
                lon=float(t["lon"]),
                hae=t.get("hae"),
                ce=t.get("ce"),
                le=t.get("le"),
                time=source_time,
                stale=None,
                confidence=t.get("confidence"),
                remarks=t.get("remarks"),
                source=t.get("source"),
                geometry_kind=geom_kind,
                geometry_quality=geometry_quality,
                ellipse=ellipse_obj,
                polygon_vertices=poly_vertices,
                custom_fields=dict(t.get("custom_fields") or {}),
            )
            row = create_target(session, ws.id, board.id, initial_col.id, target)
            # The repo sets created/updated to now_utc; rewind to source_time
            # so the demo audit chain is coherent.
            row.created_at = source_time
            row.updated_at = source_time
            session.add(row)

            # Record the creation event at source_time
            _record_audit(
                session,
                workspace_id=ws.id,
                target_id=row.id,
                actor_id=actor_id,
                event_type="created",
                occurred_at=source_time,
                to_column_id=initial_col.id,
                metadata={"scenario": scenario_id},
            )
            targets_created += 1

            # Replay transitions in order
            current_col = initial_col
            for trans in t.get("transitions") or []:
                next_col = cols_by_name[str(trans["to_column"])]
                t_minutes_ago = int(trans.get("minutes_ago", 0))
                t_when = when_now - timedelta(minutes=t_minutes_ago)
                row.column_id = next_col.id
                row.version += 1
                row.updated_at = t_when
                session.add(row)
                meta: dict[str, Any] = {"scenario": scenario_id}
                if "approving_role" in trans:
                    meta["approving_role"] = trans["approving_role"]
                _record_audit(
                    session,
                    workspace_id=ws.id,
                    target_id=row.id,
                    actor_id=actor_id,
                    event_type="transitioned",
                    occurred_at=t_when,
                    from_column_id=current_col.id,
                    to_column_id=next_col.id,
                    justification=trans.get("justification"),
                    metadata=meta,
                )
                current_col = next_col
                transitions_replayed += 1

        session.commit()

    return {
        "status": "seeded",
        "scenario": scenario_id,
        "workspace_id": str(ws.id),
        "board_name": board_name,
        "targets_created": targets_created,
        "transitions_replayed": transitions_replayed,
        "publishers_created": publishers_created,
    }
