"""App settings via pydantic-settings.

Twelve-factor: everything injectable from environment. Defaults are
hobbyist-friendly: SQLite file in /data, single admin user from env.
"""

from __future__ import annotations

import secrets

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Override via TW_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="TW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = Field(default="dev", description="Deployment env tag: dev|staging|prod.")
    database_url: str = Field(
        default="sqlite:///./tw.db",
        description="SQLAlchemy URL. SQLite for hobby, Postgres+PostGIS for prod.",
    )
    database_worker_count: int = Field(
        default=1,
        ge=1,
        description=(
            "Application worker count used to size the Postgres SQLAlchemy pool "
            "(pool_size = workers * 2 + 4)."
        ),
    )
    database_connection_warn_threshold: int = Field(
        default=0,
        ge=0,
        description=(
            "Dev-only warning threshold for simultaneously checked-out DB connections. "
            "0 disables the warning."
        ),
    )
    log_format: str = Field(default="console", description="Log format: console|json.")

    # MVP single-admin bootstrap
    admin_email: str = Field(
        default="admin@example.com",
        description="Bootstrap admin login identifier; used to seed the User row on first boot.",
    )
    admin_password: str = Field(
        default="changeme",
        description="Bootstrap admin password (env-only). Hashed via bcrypt at boot.",
    )
    bcrypt_rounds: int = Field(
        default=12,
        ge=4,
        le=31,
        description=(
            "Requested bcrypt cost. Values below the production floor are honored only "
            "when TW_ENV=test."
        ),
    )

    session_secret: str = Field(
        default_factory=lambda: secrets.token_urlsafe(48),
        description="Session cookie signing secret. SET EXPLICITLY in production.",
    )
    session_cookie_name: str = Field(default="tw_session")
    session_max_age_seconds: int = Field(default=60 * 60 * 8)  # 8h

    cors_origins: list[str] = Field(
        default_factory=lambda: [
            # SPA dev server
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            # tw-auk: mobile shells. Capacitor (iOS WKWebView, Android) and
            # Tauri both serve assets from custom schemes that the browser
            # treats as cross-origin. Including them in the default keeps
            # the mobile MVP unblocked without per-deployment config.
            "capacitor://localhost",
            "ionic://localhost",
            "https://localhost",
            "tauri://localhost",
        ],
        description=(
            "Allowed origins for the web SPA dev server + mobile shells. Production sets via env."
        ),
    )

    demo_scenarios: str = Field(
        default="",
        description=(
            "Comma-separated list of scenario IDs to seed at boot (e.g. "
            "'tf-dagger-f3ead,le-counter-narco,sar-missing-hiker'). "
            "Empty disables seeding. Idempotent — already-seeded boards are not re-seeded."
        ),
    )

    # tw-bux: where /v1/capture writes uploaded photos. Empty falls back
    # to a per-process temp dir on first use.
    captures_dir: str = Field(
        default="",
        description=(
            "Directory for /v1/capture photo storage. Empty defaults to "
            "$XDG_DATA_HOME/tw/captures or /tmp/tw-captures."
        ),
    )

    # tw-45s: optional override for the Cesium/Leaflet tile source.
    # Default empty = frontend falls back to its bundled Natural Earth
    # tile pyramid. Set to e.g. https://tile.openstreetmap.org/{z}/{x}/{y}.png
    # or a self-hosted TMS / WMS / Mapbox endpoint.
    map_tile_url: str = Field(default="", description="Tile URL template; empty = bundled.")

    # tw-fn7a: password policy knobs. Defaults align with NIST SP 800-63B
    # (length-only, no composition requirements, no expiry). Tighten via
    # env for CJIS / FedRAMP environments.
    password_min_length: int = Field(default=8, ge=1, le=128)
    password_require_mixed_case: bool = Field(default=False)
    password_require_digit: bool = Field(default=False)
    password_require_special: bool = Field(default=False)

    # WebAuthn / passkeys. Empty values derive from the request host/origin,
    # which keeps local dev and preview deployments usable without env churn.
    webauthn_rp_id: str = Field(default="")
    webauthn_origin: str = Field(default="")


_settings: Settings | None = None


def get_settings() -> Settings:
    """Module-level cached Settings.

    Tests can override by setting environment variables before app boot.
    """
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_cache() -> None:
    """Reset the cached Settings — used in tests."""
    global _settings  # noqa: PLW0603
    _settings = None


def secure_cookies_for_env(env: str) -> bool:
    """Return whether auth cookies should require HTTPS transport."""
    return env not in {"dev", "test"}
