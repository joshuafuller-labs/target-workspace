"""Tests for SPA asset response headers (tw-23b regression).

Bug shipped earlier in the session: _precompressed_response passed
filename=candidate.name to FastAPI's FileResponse, which sets
`Content-Disposition: attachment; filename=…`. Chromium ignores that
for <script src=…> via the HTML parser fast path; Safari (and some
Firefox configs) refuses to execute and the SPA silently fails to
mount — manifesting as "old behavior, won't update."

These tests pin the contract: no Content-Disposition: attachment on
served SPA assets. content-type stays as text/javascript or text/css
(matching the underlying file, not the .br/.gz suffix). Pre-compressed
variants advertise Content-Encoding correctly.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_with_spa(tmp_path: Path) -> Iterator[TestClient]:
    """Boot create_app() against a fresh DB. Requires a built SPA at
    frontend/dist (skip if missing — these tests gate browser-served
    contracts and don't apply when dev hasn't built the SPA yet)."""
    db = tmp_path / "spa.db"
    os.environ["TW_DATABASE_URL"] = f"sqlite:///{db}"
    os.environ["TW_DEMO_SCENARIOS"] = ""
    os.environ["TW_ADMIN_EMAIL"] = "admin@example.com"
    os.environ["TW_ADMIN_PASSWORD"] = "test-pw"
    os.environ["TW_SESSION_SECRET"] = "x" * 40

    import target_workspace.api.config as cfg

    cfg.reset_settings_cache()

    import importlib

    app_module = importlib.import_module("target_workspace.api.app")
    assert app_module.__file__ is not None
    repo_root = Path(app_module.__file__).resolve().parents[3]
    spa_dir = repo_root / "frontend" / "dist"
    if not (spa_dir / "assets").is_dir():
        pytest.skip("SPA not built — `npm --prefix frontend run build` first")

    from target_workspace.api.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c
    for k in (
        "TW_DATABASE_URL",
        "TW_ADMIN_EMAIL",
        "TW_ADMIN_PASSWORD",
        "TW_SESSION_SECRET",
        "TW_DEMO_SCENARIOS",
    ):
        os.environ.pop(k, None)


def _first_js_asset_with_compression(spa_dir: Path) -> str:
    """Find a real JS asset in dist/ with both .br and .gz siblings.
    Returns the path-relative-to-/assets like 'index-DvbfCbcu.js'."""
    for js in (spa_dir / "assets").glob("*.js"):
        if (js.parent / (js.name + ".br")).is_file() and (js.parent / (js.name + ".gz")).is_file():
            return js.name
    pytest.fail("no built JS asset with .br + .gz siblings found")


def _spa_dir() -> Path:
    import importlib

    app_module = importlib.import_module("target_workspace.api.app")
    assert app_module.__file__ is not None
    return Path(app_module.__file__).resolve().parents[3] / "frontend" / "dist"


def test_js_asset_has_no_content_disposition_attachment(
    client_with_spa: TestClient,
) -> None:
    """The core regression. content-disposition: attachment causes
    Safari to refuse execution of the script. Asset routes must not
    set it."""
    # Use the dev TestClient — no compression so we exercise the
    # uncompressed fallback path.
    asset = _first_js_asset_with_compression(_spa_dir())
    r = client_with_spa.get(f"/assets/{asset}")
    assert r.status_code == 200
    # Either no header at all, or anything OTHER than attachment.
    cd = r.headers.get("content-disposition", "")
    assert "attachment" not in cd.lower(), (
        f"Content-Disposition must not be `attachment` for SPA assets "
        f"(Safari refuses to execute); got {cd!r}"
    )


def test_js_asset_content_type_is_text_javascript(
    client_with_spa: TestClient,
) -> None:
    """Content-Type stays as the original asset's MIME (text/javascript),
    not the compression-suffix MIME. Otherwise the browser tries to
    parse the body as application/x-brotli or whatever, fails."""
    asset = _first_js_asset_with_compression(_spa_dir())
    r = client_with_spa.get(f"/assets/{asset}")
    assert "javascript" in r.headers["content-type"].lower()


def test_brotli_response_advertises_content_encoding(
    client_with_spa: TestClient,
) -> None:
    """When the client advertises br support and the .br sibling
    exists, the response must include Content-Encoding: br AND the
    underlying body's content-type (text/javascript)."""
    asset = _first_js_asset_with_compression(_spa_dir())
    r = client_with_spa.get(
        f"/assets/{asset}",
        headers={"Accept-Encoding": "br"},
    )
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "br"
    assert "javascript" in r.headers["content-type"].lower()
    cd = r.headers.get("content-disposition", "")
    assert "attachment" not in cd.lower()


def test_brotli_response_is_immutable_cached(
    client_with_spa: TestClient,
) -> None:
    """Hashed asset bundles are immutable; Vite stamps each with a
    content hash. The long-cache header is the perf optimization that
    landed alongside this fix."""
    asset = _first_js_asset_with_compression(_spa_dir())
    r = client_with_spa.get(
        f"/assets/{asset}",
        headers={"Accept-Encoding": "br"},
    )
    cache = r.headers.get("cache-control", "")
    assert "immutable" in cache
    assert "max-age=" in cache
