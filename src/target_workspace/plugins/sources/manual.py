"""Manual entry Source — operator submits Targets via the web form.

The simplest Source; serves as the always-there fallback so the system runs
with no external integrations configured. POST /v1/targets is its
transport; this adapter normalizes the payload coming in via the API.
"""

from __future__ import annotations

from typing import Any

from target_workspace.plugins.loader import register_source


class ManualSource:
    name = "manual"

    def normalize(
        self,
        payload: dict[str, Any],
        normalization_map: dict[str, Any],
    ) -> dict[str, Any]:
        """Manual entry already arrives in Target-shaped form via the API schema."""
        _ = normalization_map  # unused; manual entry uses the API schema directly
        return payload


register_source(ManualSource.name, ManualSource)
