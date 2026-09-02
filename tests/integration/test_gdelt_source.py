"""GDELT 2.0 Source adapter (tw-s8kd).

Maps a parsed GDELT 2.0 event row (column dict) to a Target dict.
The CSV fetch / unzip layer is out of scope here — exercising the
normalize transform on a single row is enough to lock the shape.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.fast]


_SAMPLE_ROW = {
    "GlobalEventID": "1234567890",
    "SQLDATE": "20260518",
    "EventCode": "0871",  # CAMEO: 'Reduce or break diplomatic relations'
    "EventBaseCode": "087",
    "EventRootCode": "08",
    "QuadClass": "3",  # 3 = MATERIAL_CONFLICT
    "GoldsteinScale": "-7.0",
    "Actor1Name": "GOVT",
    "Actor2Name": "REBELS",
    "ActionGeo_Lat": "35.6",
    "ActionGeo_Long": "-82.55",
    "ActionGeo_Fullname": "Asheville, NC, US",
    "SOURCEURL": "https://example.com/article",
}


def test_normalize_returns_target_shape() -> None:
    from target_workspace.plugins.sources.gdelt import GdeltSource

    src = GdeltSource()
    out = src.normalize(_SAMPLE_ROW, normalization_map={})
    assert out["lat"] == 35.6
    assert out["lon"] == -82.55
    assert out["source"] == "https://example.com/article"
    assert "GOVT" in out["name"]
    assert "REBELS" in out["name"]


def test_normalize_carries_cameo_fields() -> None:
    from target_workspace.plugins.sources.gdelt import GdeltSource

    src = GdeltSource()
    out = src.normalize(_SAMPLE_ROW, normalization_map={})
    cf = out["custom_fields"]
    assert cf["cameo_code"] == "0871"
    assert cf["actor1"] == "GOVT"
    assert cf["actor2"] == "REBELS"
    assert cf["quad_class"] == 3
    assert cf["goldstein_scale"] == -7.0
    assert cf["place"] == "Asheville, NC, US"


def test_normalize_handles_missing_actors() -> None:
    from target_workspace.plugins.sources.gdelt import GdeltSource

    row = dict(_SAMPLE_ROW)
    row["Actor1Name"] = ""
    row["Actor2Name"] = ""
    src = GdeltSource()
    out = src.normalize(row, normalization_map={})
    assert out["name"]  # produced something usable


def test_normalize_handles_blank_coords() -> None:
    """Some GDELT rows have blank lat/lon — geocoding failed upstream."""
    from target_workspace.plugins.sources.gdelt import GdeltSource

    row = dict(_SAMPLE_ROW)
    row["ActionGeo_Lat"] = ""
    row["ActionGeo_Long"] = ""
    src = GdeltSource()
    out = src.normalize(row, normalization_map={})
    assert out["lat"] == 0.0
    assert out["lon"] == 0.0


def test_normalize_sets_default_cot_type() -> None:
    from target_workspace.plugins.sources.gdelt import GdeltSource

    src = GdeltSource()
    out = src.normalize(_SAMPLE_ROW, normalization_map={})
    assert out["cot_type"] == "a-u-G-I"
