"""CORS allow-list mobile awareness (tw-auk).

Default cors_origins now includes mobile-shell schemes so the
mobile MVP doesn't need per-deployment config to load the SPA shell:

  - capacitor://localhost (iOS WKWebView, Android)
  - ionic://localhost
  - https://localhost (some Capacitor configs)
  - tauri://localhost
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.fast]


def test_default_cors_origins_includes_capacitor() -> None:
    from target_workspace.api.config import Settings

    s = Settings()
    origins = set(s.cors_origins)
    assert "capacitor://localhost" in origins


def test_default_cors_origins_includes_tauri() -> None:
    from target_workspace.api.config import Settings

    s = Settings()
    origins = set(s.cors_origins)
    assert "tauri://localhost" in origins


def test_default_cors_origins_still_includes_dev_server() -> None:
    from target_workspace.api.config import Settings

    s = Settings()
    origins = set(s.cors_origins)
    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:5173" in origins
