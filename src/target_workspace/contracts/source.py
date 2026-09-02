"""Source plugin contract — adapters that ingest detections into the workspace.

Examples: manual entry web form, HTTP webhook, CoT-in TCP/UDP listener.

Per ADR 0005, implementations are discovered via the
`target_workspace.sources` entry-points group and validated by
`tests/contract/test_source_conformance.py`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Source(Protocol):
    """A Source ingests detection events from somewhere into the workspace.

    Implementations declare a stable `name`, an optional per-instance
    configuration schema, and a `normalize(payload)` that maps raw input to
    a Target-compatible dict the workflow engine can promote.
    """

    name: str
    """Stable identifier for this adapter type, e.g. "manual", "http_webhook"."""

    def normalize(
        self,
        payload: dict[str, Any],
        normalization_map: dict[str, Any],
    ) -> dict[str, Any]:
        """Convert raw source payload into Target-shaped dict.

        `normalization_map` is the per-Source mapping rules (e.g. jq/jmespath
        expressions) supplied by the workspace owner. Implementations may
        ignore the map for adapters whose payloads are already canonical.
        """
        ...
