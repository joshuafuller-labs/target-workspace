"""ACLED conflict-event Source adapter (tw-kb2j).

Maps a parsed ACLED event row (column dict, post-API-pull) to a
Target dict. Authentication + paging happen upstream — this is the
normalize-only transform so curated scenarios can seed it.

ACLED field reference: https://acleddata.com/resources/general-guides/
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.fast]


_SAMPLE_EVENT = {
    "data_id": "10000001",
    "event_date": "2026-05-17",
    "event_type": "Battles",
    "sub_event_type": "Armed clash",
    "actor1": "Military Forces of Ukraine",
    "actor2": "Military Forces of Russia",
    "interaction": "11",
    "country": "Ukraine",
    "admin1": "Donetsk",
    "location": "Pokrovsk",
    "latitude": "48.279",
    "longitude": "37.176",
    "fatalities": "4",
    "notes": "Forces clashed near the rail junction.",
    "source": "Reuters",
    "source_scale": "International",
}


def test_normalize_returns_target_shape() -> None:
    from target_workspace.plugins.sources.acled import AcledSource

    src = AcledSource()
    out = src.normalize(_SAMPLE_EVENT, normalization_map={})
    assert out["lat"] == 48.279
    assert out["lon"] == 37.176
    assert "Pokrovsk" in out["name"]
    assert out["remarks"] == "Forces clashed near the rail junction."


def test_normalize_carries_acled_fields() -> None:
    from target_workspace.plugins.sources.acled import AcledSource

    src = AcledSource()
    out = src.normalize(_SAMPLE_EVENT, normalization_map={})
    cf = out["custom_fields"]
    assert cf["event_type"] == "Battles"
    assert cf["sub_event_type"] == "Armed clash"
    assert cf["actor1"] == "Military Forces of Ukraine"
    assert cf["actor2"] == "Military Forces of Russia"
    assert cf["country"] == "Ukraine"
    assert cf["fatalities"] == 4
    assert cf["source_publication"] == "Reuters"


def test_normalize_handles_zero_fatalities() -> None:
    from target_workspace.plugins.sources.acled import AcledSource

    row = dict(_SAMPLE_EVENT)
    row["fatalities"] = "0"
    src = AcledSource()
    out = src.normalize(row, normalization_map={})
    assert out["custom_fields"]["fatalities"] == 0


def test_normalize_default_cot_type() -> None:
    from target_workspace.plugins.sources.acled import AcledSource

    src = AcledSource()
    out = src.normalize(_SAMPLE_EVENT, normalization_map={})
    assert out["cot_type"] == "a-h-G-I"


def test_normalize_handles_blank_actor2() -> None:
    """Some ACLED rows (riots, protests) have no second actor."""
    from target_workspace.plugins.sources.acled import AcledSource

    row = dict(_SAMPLE_EVENT)
    row["actor2"] = ""
    src = AcledSource()
    out = src.normalize(row, normalization_map={})
    assert out["custom_fields"]["actor2"] is None
