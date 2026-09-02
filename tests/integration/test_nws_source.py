"""NWS / NOAA weather-alerts source adapter (tw-sfu0).

Maps a NWS GeoJSON Feature to a Target-shaped dict. Polygon geometry
preserved as polygon_vertices; severity stashed in custom_fields.

Real network calls (api.weather.gov) are not exercised here — the
normalize step is purely transformational on a sample payload.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


_SAMPLE_FEATURE = {
    "type": "Feature",
    "id": "urn:oid:2.49.0.1.840.0.fake.001",
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [-82.6, 35.5],
                [-82.4, 35.5],
                [-82.4, 35.7],
                [-82.6, 35.7],
                [-82.6, 35.5],
            ],
        ],
    },
    "properties": {
        "event": "Flood Warning",
        "headline": "Flood Warning issued for Buncombe County",
        "severity": "Severe",
        "certainty": "Observed",
        "urgency": "Immediate",
        "areaDesc": "Buncombe County, NC",
        "effective": "2026-05-18T14:00:00-04:00",
        "ends": "2026-05-19T02:00:00-04:00",
        "senderName": "NWS Greenville-Spartanburg SC",
    },
}


def test_normalize_returns_target_shape() -> None:
    from target_workspace.plugins.sources.nws import NwsSource

    src = NwsSource()
    out = src.normalize(_SAMPLE_FEATURE, normalization_map={})
    assert out["name"] == "Flood Warning issued for Buncombe County"
    assert out["geometry_kind"] == "polygon"
    assert isinstance(out["polygon_vertices"], list)
    assert len(out["polygon_vertices"]) == 5
    # Approx-centroid coords landed in lat/lon
    assert -82.7 < out["lon"] < -82.3
    assert 35.4 < out["lat"] < 35.8


def test_normalize_carries_severity_to_custom_fields() -> None:
    from target_workspace.plugins.sources.nws import NwsSource

    src = NwsSource()
    out = src.normalize(_SAMPLE_FEATURE, normalization_map={})
    cf = out["custom_fields"]
    assert cf["severity"] == "Severe"
    assert cf["event"] == "Flood Warning"
    assert cf["area"] == "Buncombe County, NC"
    assert cf["urgency"] == "Immediate"
    assert cf["effective"] == "2026-05-18T14:00:00-04:00"
    assert cf["ends"] == "2026-05-19T02:00:00-04:00"


def test_normalize_multipolygon_uses_first_ring() -> None:
    from target_workspace.plugins.sources.nws import NwsSource

    feat: dict[str, Any] = dict(_SAMPLE_FEATURE)
    feat["geometry"] = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[-82.6, 35.5], [-82.4, 35.5], [-82.4, 35.7], [-82.6, 35.5]]],
            [[[-83.0, 36.0], [-82.8, 36.0], [-82.8, 36.2], [-83.0, 36.0]]],
        ],
    }
    src = NwsSource()
    out = src.normalize(feat, normalization_map={})
    assert out["geometry_kind"] == "polygon"
    assert len(out["polygon_vertices"]) == 4


def test_normalize_handles_missing_geometry() -> None:
    """Some alerts (small craft advisory) ship without geometry; the
    adapter should still produce a Target — geometry_kind 'point' with
    NaN-safe placeholder."""
    from target_workspace.plugins.sources.nws import NwsSource

    feat: dict[str, Any] = dict(_SAMPLE_FEATURE)
    feat["geometry"] = None
    src = NwsSource()
    out = src.normalize(feat, normalization_map={})
    assert out["geometry_kind"] == "point"
    assert out["lat"] == 0.0
    assert out["lon"] == 0.0
    assert out["polygon_vertices"] is None
