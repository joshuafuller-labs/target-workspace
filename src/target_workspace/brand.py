"""Single source of truth for the product name.

The project name isn't settled — we may rebrand before launch. Every
user-visible string that hard-codes "Target Workspace" goes through this
constant so a future rename is a one-line change (or one env var).

Override at boot via `TW_BRAND_NAME`:

    TW_BRAND_NAME="Acme Targeting" uvicorn ...

The frontend has its own mirror (`frontend/src/brand.ts`) since the SPA
is built separately. They default to the same string; a deployer who
overrides the backend value should override the frontend value too
(via `VITE_BRAND_NAME` at build time).
"""

from __future__ import annotations

import os

BRAND_NAME: str = os.environ.get("TW_BRAND_NAME", "Target Workspace").strip() or "Target Workspace"
