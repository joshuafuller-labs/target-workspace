"""Publisher plugin contract — adapters that emit workspace events outbound.

Examples: TAK Server (CoT over TLS via pytak), raw CoT emit (TCP/UDP),
webhook out, mission package (.zip) export.

Per ADR 0005, implementations are discovered via the
`target_workspace.publishers` entry-points group and validated by
`tests/contract/test_publisher_conformance.py`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Publisher(Protocol):
    """A Publisher emits workspace events outbound."""

    name: str
    """Stable identifier for this adapter type, e.g. "tak_server", "raw_cot"."""

    def publish(self, *, target: Any, adapter_config: dict[str, Any]) -> None:
        """Best-effort emit. Raise on configuration errors; transient I/O errors
        should be retried inside the implementation. The workflow engine
        treats exceptions as non-fatal."""
        ...
