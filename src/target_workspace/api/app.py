"""FastAPI application factory + /healthz, /readyz, /metrics primitives."""

from __future__ import annotations

from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlmodel import Session, select
from starlette.middleware.gzip import GZipMiddleware

from target_workspace import __version__
from target_workspace.api.auth import hash_password
from target_workspace.api.config import Settings, get_settings
from target_workspace.api.routers import api_tokens as api_tokens_router
from target_workspace.api.routers import audit as audit_router
from target_workspace.api.routers import auth as auth_router
from target_workspace.api.routers import board_templates as board_templates_router
from target_workspace.api.routers import boards as boards_router
from target_workspace.api.routers import capture as capture_router
from target_workspace.api.routers import forms as forms_router
from target_workspace.api.routers import groups as groups_router
from target_workspace.api.routers import ingest as ingest_router
from target_workspace.api.routers import instance as instance_router
from target_workspace.api.routers import intake as intake_router
from target_workspace.api.routers import invitations as invitations_router
from target_workspace.api.routers import metrics as metrics_router
from target_workspace.api.routers import mfa as mfa_router
from target_workspace.api.routers import mfa_policy as mfa_policy_router
from target_workspace.api.routers import op_periods as op_periods_router
from target_workspace.api.routers import passkeys as passkeys_router
from target_workspace.api.routers import password_reset as password_reset_router
from target_workspace.api.routers import plugin_config as plugin_config_router
from target_workspace.api.routers import positions as positions_router
from target_workspace.api.routers import presence as presence_router
from target_workspace.api.routers import publisher_health as publisher_health_router
from target_workspace.api.routers import realtime as realtime_router
from target_workspace.api.routers import resources as resources_router
from target_workspace.api.routers import safety as safety_router
from target_workspace.api.routers import targets as targets_router
from target_workspace.api.routers import users as users_router
from target_workspace.api.routers import workflow_triggers as workflow_triggers_router
from target_workspace.api.routers import workspace_export as workspace_export_router
from target_workspace.api.routers import workspace_settings as workspace_settings_router
from target_workspace.brand import BRAND_NAME
from target_workspace.db import create_tables, init_db
from target_workspace.db.engine import create_engine_for_url, reset_engine
from target_workspace.db.tables import UserTable, WorkspaceTable


def create_app(settings: Settings | None = None) -> FastAPI:  # noqa: PLR0915 — app factory wires many routers/middleware; linear setup is clearer than fragmenting
    """Build a FastAPI app instance.

    Configured at boot — runs alembic upgrade head, then creates any
    missing tables only in dev for models that haven't been migrated yet,
    then seeds a single admin user / workspace if none exist. Idempotent on
    restart.
    """
    s = settings or get_settings()
    engine = init_db(
        s.database_url,
        worker_count=s.database_worker_count,
        connection_warn_threshold=(
            s.database_connection_warn_threshold
            if s.env == "dev" and s.database_connection_warn_threshold > 0
            else None
        ),
    )
    _run_alembic_upgrade(s.database_url, env=s.env)
    # create_all is a dev-only convenience for local iteration. Non-dev must
    # fail closed on migration/schema drift instead of serving against an
    # unknown database contract.
    if s.env == "dev":
        create_tables(engine)
    _ensure_bootstrap_user(engine, s)
    _seed_demo_scenarios(engine, s)
    _backfill_legacy_audit_chain(engine)
    # tw-ngn5: register the default LoggingTrigger so the audit pipeline
    # has at least one tap from boot. Idempotent — safe under create_app
    # being called multiple times in test fixtures.
    from target_workspace.api.triggers import install_default_triggers  # noqa: PLC0415

    install_default_triggers()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Any:
        """FastAPI lifespan — start/stop background tasks. CoT-in
        TCP listeners are launched here per configured SourceConfig
        and torn down on shutdown. tw-o13."""
        import asyncio as _asyncio  # noqa: PLC0415

        servers = await _start_cot_in_listeners(engine)
        try:
            yield
        finally:
            for server in servers:
                server.close()
            for server in servers:
                with suppress(TimeoutError):
                    await _asyncio.wait_for(server.wait_closed(), timeout=2.0)
            engine.dispose()
            reset_engine()

    app = FastAPI(
        title=BRAND_NAME,
        version=__version__,
        description=(
            "Configurable kanban for the target lifecycle. CoT-native, "
            "plugin-driven, malleable. See docs/foundation.md for principles."
        ),
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
        redoc_url="/v1/redoc",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # tw-33g: structured errors per RFC 7807. Only HTTPException is
    # reformatted; pydantic RequestValidationError keeps FastAPI's
    # default shape so clients that already parse it don't break.
    from http import HTTPStatus as _HTTPStatus  # noqa: PLC0415

    from fastapi import HTTPException as _HTTPException  # noqa: PLC0415
    from fastapi.responses import JSONResponse as _JSONResponse  # noqa: PLC0415
    from starlette.requests import Request as _Request  # noqa: PLC0415

    def _slug(name: str) -> str:
        return name.lower().replace(" ", "-")

    @app.exception_handler(_HTTPException)
    async def _problem_detail_handler(
        request: _Request,
        exc: _HTTPException,
    ) -> _JSONResponse:
        title = _HTTPStatus(exc.status_code).phrase
        body = {
            "type": f"/v1/problems/{_slug(title)}",
            "title": title,
            "status": exc.status_code,
            "detail": str(exc.detail) if exc.detail else title,
            "instance": str(request.url.path),
        }
        return _JSONResponse(
            status_code=exc.status_code,
            content=body,
            media_type="application/problem+json",
            headers=dict(exc.headers or {}),
        )

    # gzip everything over 500 bytes. Brings the 4.7MB Cesium chunk down
    # to ~1.3MB and the smaller chunks proportionally — load time over a
    # slow link drops from ~50s to ~15s end-to-end. ASGI's GZipMiddleware
    # is stdlib (via Starlette) so no new dep.
    app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)

    # tw-54t: Idempotency-Key support for POST. Mobile clients on flaky
    # networks can safely retry. Cache is in-memory, single-instance.
    from starlette.middleware.base import BaseHTTPMiddleware  # noqa: PLC0415
    from starlette.responses import Response as _StarletteResponse  # noqa: PLC0415

    class _IdempotencyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
            if request.method.upper() != "POST":
                return await call_next(request)
            key = request.headers.get("Idempotency-Key")
            if not key:
                return await call_next(request)
            tw_session = request.cookies.get("tw_session", "")
            # Use the cookie value as the namespace; if missing fall back
            # to the bearer-token preview or 'anon'. Real attribution
            # happens inside route handlers but for caching purposes a
            # stable namespace per session is enough.
            bearer = request.headers.get("Authorization", "")
            namespace = tw_session[:32] or bearer[:32] or "anon"
            from target_workspace.api.idempotency import (  # noqa: PLC0415
                get_cached,
                make_key,
                store,
            )

            cache_key = make_key(
                user_id=namespace,
                path=request.url.path,
                idempotency_key=key,
            )
            cached = get_cached(cache_key)
            if cached is not None:
                status_code, body, headers = cached
                return _StarletteResponse(
                    content=body,
                    status_code=status_code,
                    headers=headers,
                )
            response = await call_next(request)
            # Read body to cache + return a fresh Response so downstream
            # consumers still see the bytes.
            body_chunks: list[bytes] = [chunk async for chunk in response.body_iterator]
            full_body = b"".join(body_chunks)
            if HTTPStatus.OK <= response.status_code < HTTPStatus.MULTIPLE_CHOICES:
                store(
                    cache_key,
                    response.status_code,
                    full_body,
                    dict(response.headers),
                )
            return _StarletteResponse(
                content=full_body,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

    app.add_middleware(_IdempotencyMiddleware)

    # tw-bkd: global per-IP write rate-limit. Reads bypass. auth.login
    # / forgot-password have their own tighter buckets.
    class _WriteRateLimitMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
            method = request.method.upper()
            if method in {"GET", "HEAD", "OPTIONS"}:
                return await call_next(request)
            path = request.url.path
            if path.startswith("/v1/auth/login") or path.startswith(
                "/v1/auth/forgot-password",
            ):
                return await call_next(request)
            client_ip = request.client.host if request.client else "unknown"
            from target_workspace.api.ratelimit import (  # noqa: PLC0415
                check_and_record,
            )

            allowed, retry = check_and_record(
                bucket="http.write.ip",
                key=client_ip,
            )
            if not allowed:
                return _StarletteResponse(
                    content=(
                        b'{"type":"/v1/problems/too-many-requests",'
                        b'"title":"Too Many Requests","status":429,'
                        b'"detail":"write rate limit exceeded"}'
                    ),
                    status_code=429,
                    headers={
                        "Content-Type": "application/problem+json",
                        "Retry-After": str(retry),
                    },
                )
            return await call_next(request)

    app.add_middleware(_WriteRateLimitMiddleware)

    app.include_router(auth_router.router)
    app.include_router(boards_router.router)
    app.include_router(targets_router.router)
    app.include_router(audit_router.router)
    app.include_router(realtime_router.router)
    app.include_router(ingest_router.router)
    app.include_router(users_router.router)
    app.include_router(instance_router.router)
    app.include_router(workspace_export_router.router)
    app.include_router(capture_router.router)
    app.include_router(forms_router.router)
    app.include_router(invitations_router.router)
    app.include_router(invitations_router.auth_router)
    app.include_router(password_reset_router.router)
    app.include_router(passkeys_router.router)
    app.include_router(groups_router.router)
    app.include_router(api_tokens_router.router)
    app.include_router(board_templates_router.router)
    app.include_router(board_templates_router.clone_router)
    app.include_router(mfa_router.router)
    app.include_router(mfa_policy_router.router)
    app.include_router(plugin_config_router.plugins_router)
    app.include_router(plugin_config_router.sources_router)
    app.include_router(plugin_config_router.publishers_router)
    app.include_router(op_periods_router.router)
    app.include_router(positions_router.router)
    app.include_router(presence_router.router)
    app.include_router(safety_router.router)
    app.include_router(metrics_router.router)
    app.include_router(resources_router.router)
    app.include_router(publisher_health_router.router)
    app.include_router(workflow_triggers_router.router)
    app.include_router(intake_router.router)
    app.include_router(workspace_settings_router.router)

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, Any]:
        return {"status": "ok", "version": __version__}

    @app.get("/readyz", tags=["meta"])
    def readyz(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
        ok = True
        details: dict[str, str] = {}
        engine = create_engine_for_url(
            settings.database_url,
            worker_count=settings.database_worker_count,
        )
        try:
            with Session(engine) as session:
                session.exec(text("SELECT 1"))  # type: ignore[call-overload]
            details["db"] = "ok"
        except Exception as e:
            ok = False
            details["db"] = f"error: {type(e).__name__}"
        try:
            if _database_at_alembic_head(settings.database_url):
                details["schema"] = "at-head"
            else:
                ok = False
                details["schema"] = "not-at-head"
        except Exception as e:
            ok = False
            details["schema"] = f"error: {type(e).__name__}"
        finally:
            engine.dispose()
        return {"status": "ok" if ok else "degraded", "details": details}

    _mount_spa(app)
    return app


def _run_alembic_upgrade(database_url: str, *, env: str = "dev") -> None:
    """Run `alembic upgrade head` against the configured DB.

    Dev may fall back to create_all for fast local iteration. Non-dev must
    fail closed: serving traffic against an unknown schema is worse than
    refusing startup.
    """
    import logging  # noqa: PLC0415

    log = logging.getLogger(__name__)
    repo_root = Path(__file__).resolve().parents[3]
    ini = repo_root / "alembic.ini"
    if not ini.is_file():
        if env != "dev":
            msg = f"alembic.ini not found at {ini}"
            raise RuntimeError(msg)
        log.debug("alembic.ini not found at %s; skipping migration", ini)
        return
    try:
        from alembic import command  # noqa: PLC0415
        from alembic.config import Config  # noqa: PLC0415
        from sqlalchemy import inspect  # noqa: PLC0415

        cfg = Config(str(ini))
        cfg.set_main_option("sqlalchemy.url", database_url)
        cfg.set_main_option("script_location", str(repo_root / "migrations"))

        # Detect an existing deploy that pre-dates alembic adoption: DB
        # has tables but no `alembic_version`. Stamp it at head rather
        # than running the baseline migration, which would fail trying
        # to CREATE TABLE on tables that already exist.
        engine = create_engine_for_url(database_url)
        try:
            with engine.connect() as conn:
                insp = inspect(conn)
                has_tables = "workspace" in insp.get_table_names()
                has_version = "alembic_version" in insp.get_table_names()
                current_revision = ""
                if has_version:
                    row = conn.execute(
                        text("SELECT version_num FROM alembic_version LIMIT 1"),
                    ).first()
                    current_revision = str(row[0]) if row else ""
        finally:
            engine.dispose()
        if current_revision == _alembic_head_revision():
            return
        if has_tables and not has_version:
            log.info("existing pre-alembic schema detected; stamping head")
            command.stamp(cfg, "head")
        else:
            command.upgrade(cfg, "head")
    except Exception as exc:
        if env != "dev":
            msg = f"alembic upgrade failed: {exc}"
            raise RuntimeError(msg) from exc
        log.warning("alembic upgrade failed (%s); falling back to dev create_all", exc)


def _alembic_head_revision() -> str:
    repo_root = Path(__file__).resolve().parents[3]
    ini = repo_root / "alembic.ini"
    from alembic.config import Config  # noqa: PLC0415
    from alembic.script import ScriptDirectory  # noqa: PLC0415

    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if not head:
        msg = "alembic head revision is unavailable"
        raise RuntimeError(msg)
    return head


def _database_alembic_revision(database_url: str) -> str:
    engine = create_engine_for_url(database_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
        return str(row[0]) if row is not None else ""
    finally:
        engine.dispose()


def _database_at_alembic_head(database_url: str) -> bool:
    return _database_alembic_revision(database_url) == _alembic_head_revision()


async def _start_cot_in_listeners(engine: Any) -> list[Any]:
    """At app boot, scan SourceConfig rows for enabled cot_in plugins
    and start one TCP listener per row. Returns the list of asyncio
    Server instances for the lifespan to tear down on shutdown.

    Per-row config (in SourceConfig.adapter_config):
      host          default '0.0.0.0'
      port          required
      board_id      required (UUID string)
      column_id     required (UUID string)
      drop_pli      default True (filter friendly PLI broadcasts)

    Failures starting an individual listener are logged + skipped so
    one misconfigured row doesn't take the whole app down.
    """
    import logging  # noqa: PLC0415
    from uuid import UUID as _UUID  # noqa: PLC0415

    from target_workspace.db.tables import SourceConfigTable  # noqa: PLC0415
    from target_workspace.plugins.sources.cot_in_listener import (  # noqa: PLC0415
        run_listener,
    )

    log = logging.getLogger(__name__)
    servers: list[Any] = []
    try:
        with Session(engine) as session:
            session.expire_on_commit = False
            rows = session.exec(
                select(SourceConfigTable)
                .where(SourceConfigTable.plugin_type == "cot_in")
                .where(SourceConfigTable.enabled),
            ).all()
            for row in rows:
                cfg = row.adapter_config or {}
                try:
                    server = await run_listener(
                        host=str(cfg.get("host", "0.0.0.0")),  # noqa: S104 — CoT UDP listener binds all interfaces by design
                        port=int(cfg["port"]),
                        workspace_id=row.workspace_id,
                        board_id=_UUID(cfg["board_id"]),
                        column_id=_UUID(cfg["column_id"]),
                        drop_pli=bool(cfg.get("drop_pli", True)),
                    )
                    servers.append(server)
                    log.info(
                        "cot-in: started listener %s on %s:%s",
                        row.name,
                        cfg.get("host", "0.0.0.0"),  # noqa: S104 — log of the bind host above
                        cfg.get("port"),
                    )
                except Exception as exc:
                    log.warning(
                        "cot-in: failed to start listener %s: %s",
                        row.name,
                        exc,
                    )
    except Exception:
        log.exception("cot-in: lifespan startup scan failed")
    return servers


def _seed_demo_scenarios(engine: Any, settings: Settings) -> None:
    """If TW_DEMO_SCENARIOS is set, seed each scenario into the admin's workspace."""
    if not settings.demo_scenarios.strip():
        return
    from target_workspace.demo import seed_workspace  # noqa: PLC0415

    ids = [sid.strip() for sid in settings.demo_scenarios.split(",") if sid.strip()]
    for sid in ids:
        try:
            seed_workspace(engine, scenario_id=sid)
        except Exception as exc:
            import logging  # noqa: PLC0415

            logging.getLogger(__name__).warning("demo seed %r failed: %s", sid, exc)


def _backfill_legacy_audit_chain(engine: Any) -> None:
    from target_workspace.api.signing import backfill_legacy_audit_chain  # noqa: PLC0415

    with Session(engine) as session:
        backfill_legacy_audit_chain(session)
        session.commit()


def _mount_spa(app: FastAPI) -> None:
    """If the built SPA exists, serve assets and SPA-fallback non-API paths."""
    # src/target_workspace/api/app.py -> repo_root/frontend/dist
    repo_root = Path(__file__).resolve().parents[3]
    spa_dir = repo_root / "frontend" / "dist"
    if not spa_dir.exists():
        return

    # Long-cache the hashed asset bundles. Vite stamps every asset with
    # a content hash (`index-DVEJqi01.js`), so it's safe to tell browsers
    # to keep them forever — a new deploy ships a new hash, which
    # automatically busts the cache.
    _IMMUTABLE_CACHE = "public, max-age=31536000, immutable"

    def _precompressed_response(candidate: Path, accept_encoding: str) -> FileResponse:
        """Serve a pre-compressed `.br` or `.gz` variant of `candidate`
        when the client accepts it. Falls back to the raw file. We
        write these variants at build time via vite-plugin-compression2
        with max levels (br=11, gz=9) — far better than the runtime
        GZipMiddleware can do per request.

        IMPORTANT: do NOT pass `filename=` to FileResponse — it sets
        `Content-Disposition: attachment`, which tells browsers to
        download the asset rather than execute it inline. Some browsers
        ignore that for <script> tags via the HTML parser path, but
        others (Safari in particular) refuse to run the script and the
        SPA silently fails to mount. We resolve the MIME type from the
        ORIGINAL file path (before the .br / .gz suffix) instead.
        """
        import mimetypes  # noqa: PLC0415

        mt, _ = mimetypes.guess_type(candidate.name)
        ae = accept_encoding.lower()
        if "br" in ae:
            br = candidate.with_suffix(candidate.suffix + ".br")
            if br.is_file():
                return FileResponse(
                    br,
                    media_type=mt,
                    headers={
                        "Cache-Control": _IMMUTABLE_CACHE,
                        "Content-Encoding": "br",
                        "Vary": "Accept-Encoding",
                    },
                )
        if "gzip" in ae:
            gz = candidate.with_suffix(candidate.suffix + ".gz")
            if gz.is_file():
                return FileResponse(
                    gz,
                    media_type=mt,
                    headers={
                        "Cache-Control": _IMMUTABLE_CACHE,
                        "Content-Encoding": "gzip",
                        "Vary": "Accept-Encoding",
                    },
                )
        return FileResponse(
            candidate,
            media_type=mt,
            headers={
                "Cache-Control": _IMMUTABLE_CACHE,
                "Vary": "Accept-Encoding",
            },
        )

    @app.get("/assets/{path:path}", include_in_schema=False)
    def _spa_asset(path: str, request: Request) -> FileResponse:
        candidate = spa_dir / "assets" / path
        if not candidate.is_file():
            raise HTTPException(status_code=404)
        return _precompressed_response(candidate, request.headers.get("accept-encoding", ""))

    @app.get("/", include_in_schema=False)
    def _spa_root() -> FileResponse:
        # index.html is NEVER long-cached — it's the entry point that
        # references the hashed asset filenames. no-cache lets the
        # browser revalidate so deploys land immediately.
        return FileResponse(
            spa_dir / "index.html",
            headers={"Cache-Control": "no-store, must-revalidate"},
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_fallback(full_path: str, request: Request) -> FileResponse:
        candidate = spa_dir / full_path
        if candidate.is_file():
            # Cesium static files and other hashed assets get the long
            # cache + pre-compressed serving. SPA routes fall back to
            # index.html with no-cache.
            return _precompressed_response(candidate, request.headers.get("accept-encoding", ""))
        return FileResponse(
            spa_dir / "index.html",
            headers={"Cache-Control": "no-store, must-revalidate"},
        )


def _ensure_bootstrap_user(engine: Any, settings: Settings) -> None:
    """Seed a single admin user + workspace if the DB is empty."""
    with Session(engine) as session:
        session.expire_on_commit = False
        any_user = session.exec(select(UserTable)).first()
        if any_user is not None:
            return
        ws = WorkspaceTable(name="Default", created_at=datetime.now(tz=UTC))
        session.add(ws)
        session.flush()
        user = UserTable(
            id=uuid4(),
            workspace_id=ws.id,
            email=settings.admin_email,
            display_name="Admin",
            role="admin",
            password_hash=hash_password(
                settings.admin_password,
                env=settings.env,
                bcrypt_rounds=settings.bcrypt_rounds,
            ),
            created_at=datetime.now(tz=UTC),
        )
        session.add(user)
        session.commit()


# NOTE: no module-level `app = create_app()`. Use uvicorn's --factory
# mode against `create_app`: `uvicorn --factory target_workspace.api.app:create_app`.
#
# Why no eager app: importing this module triggered alembic + table
# creation against whatever TW_DATABASE_URL was set at IMPORT time —
# including silent failure when env wasn't yet configured (test
# collection order!). Factory mode defers creation until uvicorn calls
# the factory, which is the only call site that should drive boot.
