"""Coverage for the simple Source adapters + the webhook_out publisher.

These are pure data-mapping (normalize) functions plus one HTTP POST; the
happy-path + edge branches are covered here without network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from target_workspace.models.target import Target
from target_workspace.plugins.publishers import webhook_out as wh
from target_workspace.plugins.sources.acled import AcledSource, _safe_float, _safe_int
from target_workspace.plugins.sources.gdelt import GdeltSource
from target_workspace.plugins.sources.manual import ManualSource
from target_workspace.plugins.sources.nws import NwsSource, _centroid, _extract_geometry

pytestmark = [pytest.mark.fast]


def test_safe_float_and_int_edges() -> None:
    assert _safe_float("3.5") == 3.5
    assert _safe_float("") == 0.0
    assert _safe_float("nope") == 0.0
    assert _safe_float(None) == 0.0
    assert _safe_int("7") == 7
    assert _safe_int("") == 0
    assert _safe_int("x") == 0


def test_acled_normalize_full_and_fallback() -> None:
    out = AcledSource().normalize(
        {
            "event_type": "Battles",
            "location": "Kharkiv",
            "latitude": "49.99",
            "longitude": "36.23",
            "actor1": "Mil A",
            "fatalities": "4",
            "notes": "n",
            "data_id": "1",
        },
        {},
    )
    assert out["name"] == "Battles — Kharkiv"
    assert out["lat"] == 49.99 and out["cot_type"] == "a-h-G-I"
    assert out["custom_fields"]["fatalities"] == 4 and out["custom_fields"]["actor1"] == "Mil A"
    # fallback name when no event_type/location
    fb = AcledSource().normalize({"data_id": "42"}, {})
    assert "42" in fb["name"]


def test_gdelt_normalize_name_variants() -> None:
    g = GdeltSource()
    a = g.normalize({"Actor1Name": "A", "Actor2Name": "B", "ActionGeo_Fullname": "Place"}, {})
    assert a["name"] == "A / B — Place" and a["cot_type"] == "a-u-G-I"
    b = g.normalize({"ActionGeo_Fullname": "OnlyPlace"}, {})
    assert b["name"] == "OnlyPlace"
    c = g.normalize({"GlobalEventID": "99"}, {})
    assert "99" in c["name"]
    assert c["custom_fields"]["quad_class"] is None  # _safe_int("") -> None


def test_nws_geometry_variants() -> None:
    n = NwsSource()
    poly = {
        "properties": {"headline": "Flood", "event": "Flood Warning"},
        "geometry": {"type": "Polygon", "coordinates": [[[0.0, 0.0], [2.0, 0.0], [2.0, 2.0]]]},
    }
    out = n.normalize(poly, {})
    assert out["geometry_kind"] == "polygon" and out["name"] == "Flood"
    assert out["polygon_vertices"][0] == [0.0, 0.0]
    # MultiPolygon
    mp = {
        "properties": {},
        "geometry": {"type": "MultiPolygon", "coordinates": [[[[1.0, 1.0], [3.0, 1.0]]]]},
    }
    assert n.normalize(mp, {})["geometry_kind"] == "polygon"
    # no / non-polygon geometry -> point fallback
    assert n.normalize({"properties": {}, "geometry": None}, {})["geometry_kind"] == "point"
    assert _extract_geometry({"type": "LineString"})[1] == "point"
    assert _centroid([]) == (0.0, 0.0)


def test_manual_normalize_passthrough() -> None:
    payload = {"name": "x", "lat": 1.0}
    assert ManualSource().normalize(payload, {"ignored": True}) is payload


def _target() -> Target:
    return Target(
        name="HOOKME",
        cot_type="a-h-G",
        lat=1.0,
        lon=2.0,
        time=datetime(2026, 5, 16, tzinfo=UTC),
        confidence=0.5,
    )


def test_webhook_out_requires_url() -> None:
    with pytest.raises(ValueError, match="requires `url`"):
        wh.WebhookOutPublisher().publish(target=_target(), adapter_config={})


def test_webhook_out_posts_target_json(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _FakeClient:
        def __init__(self, *_a: Any, **_k: Any) -> None: ...
        def __enter__(self) -> _FakeClient:
            return self

        def __exit__(self, *_a: object) -> None: ...
        def request(self, method: str, url: str, *, json: Any, headers: Any) -> None:
            captured.update(method=method, url=url, json=json, headers=headers)

    monkeypatch.setattr("target_workspace.plugins.publishers.webhook_out.httpx.Client", _FakeClient)
    wh.WebhookOutPublisher().publish(
        target=_target(),
        adapter_config={"url": "https://h/hook", "headers": {"X-K": "v"}, "method": "put"},
    )
    assert captured["method"] == "PUT" and captured["url"] == "https://h/hook"
    assert captured["headers"] == {"X-K": "v"}
    assert captured["json"]["name"] == "HOOKME" and captured["json"]["lat"] == 1.0
