"""USGS earthquake feed Source adapter (tw-8zfi).

Maps a USGS GeoJSON Feature (from earthquake.usgs.gov) to a Target.
Real network calls aren't exercised — the normalize transform is the
unit under test.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.fast]


_SAMPLE_FEATURE = {
    "type": "Feature",
    "id": "us7000fake",
    "properties": {
        "mag": 5.2,
        "place": "26km W of Sand Point, Alaska",
        "time": 1747600000000,  # ms epoch
        "updated": 1747600300000,
        "tsunami": 0,
        "felt": 23,
        "title": "M 5.2 - 26km W of Sand Point, Alaska",
        "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000fake",
    },
    "geometry": {
        "type": "Point",
        "coordinates": [-160.95, 55.34, 22.5],  # lon, lat, depth_km
    },
}


def test_normalize_returns_target_shape() -> None:
    from target_workspace.plugins.sources.usgs import UsgsSource

    src = UsgsSource()
    out = src.normalize(_SAMPLE_FEATURE, normalization_map={})
    assert out["name"] == "M 5.2 - 26km W of Sand Point, Alaska"
    assert out["lat"] == 55.34
    assert out["lon"] == -160.95
    assert out["geometry_kind"] == "point"
    assert out["source"] == "https://earthquake.usgs.gov/earthquakes/eventpage/us7000fake"


def test_normalize_carries_seismic_fields() -> None:
    from target_workspace.plugins.sources.usgs import UsgsSource

    src = UsgsSource()
    out = src.normalize(_SAMPLE_FEATURE, normalization_map={})
    cf = out["custom_fields"]
    assert cf["magnitude"] == 5.2
    assert cf["depth_km"] == 22.5
    assert cf["place"] == "26km W of Sand Point, Alaska"
    assert cf["tsunami"] == 0
    assert cf["felt"] == 23


def test_normalize_handles_missing_depth() -> None:
    from target_workspace.plugins.sources.usgs import UsgsSource

    feat = dict(_SAMPLE_FEATURE)
    feat["geometry"] = {"type": "Point", "coordinates": [-122.4, 37.8]}
    src = UsgsSource()
    out = src.normalize(feat, normalization_map={})
    assert out["custom_fields"]["depth_km"] is None
    assert out["lat"] == 37.8
    assert out["lon"] == -122.4
