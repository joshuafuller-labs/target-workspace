"""HTTP webhook Source — external systems POST per-source bodies in.

Closes the 'we can ingest from any AI/CV/OSINT pipeline' MVP gap. Each
configured source carries:
  - a bearer token (hashed, never echoed)
  - a normalization_map that turns the raw POST body into Target fields

The normalization_map values use a tiny JSONPath dialect:
  "$.callsign"          → body["callsign"]
  "$.location.lat"      → body["location"]["lat"]
  "a-h-G-E-V"           → literal constant (no $. prefix = literal)

Why our own JSONPath instead of pulling jq/jmespath: the syntax we
need covers > 95% of real-world per-source maps, the dep saves us
from a C build + lockfile churn, and the JSONPath dialect is the
familiar one for anyone who's written a per-source ingest map.

tw-h7x.
"""

from __future__ import annotations

from typing import Any

from target_workspace.plugins.loader import register_source


class HttpWebhookSource:
    name = "http_webhook"

    def normalize(
        self,
        payload: dict[str, Any],
        normalization_map: dict[str, Any],
    ) -> dict[str, Any]:
        """Walk the normalization_map; replace each value that starts
        with `$.` with the result of extracting that JSONPath from the
        payload. Literal strings (no `$.`) are passed through as-is.

        Raises KeyError when a referenced path is absent — the caller
        translates that into a 422 with the missing path in the detail.
        """
        out: dict[str, Any] = {}
        for field, spec in normalization_map.items():
            out[field] = _resolve(spec, payload)
        return out


def _resolve(spec: Any, payload: dict[str, Any]) -> Any:
    """Resolve a single normalization_map value against `payload`."""
    if isinstance(spec, str) and spec.startswith("$."):
        path = spec[2:].split(".")
        cur: Any = payload
        for segment in path:
            if not isinstance(cur, dict) or segment not in cur:
                msg = f"normalization map references missing path: {spec}"
                raise KeyError(msg)
            cur = cur[segment]
        return cur
    # Literal — pass through (int, str, bool, list, dict, etc).
    return spec


register_source(HttpWebhookSource.name, HttpWebhookSource)
