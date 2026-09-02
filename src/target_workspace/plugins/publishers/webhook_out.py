"""Webhook-out Publisher — HTTP POST JSON payload per target.

The "I'm not on TAK, just give me an event" path. Adapter config:

  adapter_config = {
      "url": "https://example.com/hook",
      "method": "POST",
      "headers": {"X-API-Key": "..."},
      "timeout_seconds": 5,
  }
"""

from __future__ import annotations

from typing import Any

import httpx

from target_workspace.plugins.loader import register_publisher


class WebhookOutPublisher:
    name = "webhook_out"

    def publish(self, *, target: Any, adapter_config: dict[str, Any]) -> None:
        url = str(adapter_config.get("url", ""))
        if not url:
            msg = "webhook_out publisher requires `url`"
            raise ValueError(msg)
        method = str(adapter_config.get("method", "POST")).upper()
        headers = dict(adapter_config.get("headers") or {})
        timeout = float(adapter_config.get("timeout_seconds", 5.0))

        body = {
            "id": str(target.id),
            "name": target.name,
            "cot_type": target.cot_type,
            "lat": target.lat,
            "lon": target.lon,
            "time": target.time.isoformat() if hasattr(target.time, "isoformat") else target.time,
            "confidence": target.confidence,
            "version": target.version,
            "custom_fields": dict(target.custom_fields or {}),
        }
        with httpx.Client(timeout=timeout) as client:
            client.request(method, url, json=body, headers=headers)


register_publisher(WebhookOutPublisher.name, WebhookOutPublisher)
