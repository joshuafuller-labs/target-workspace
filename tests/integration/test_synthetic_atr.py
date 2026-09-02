"""Synthetic AI-ATR Source adapter (tw-cj9).

Reference Source implementation for the target.classification
convention (tw-x93). Emits a payload shaped like a Saker Scout-style
ATR output; normalize() folds it into a Target-shaped dict.

This is a plugin example — not a background timer. Demos / scenarios
invoke generate_event() on a cadence; tests just exercise the helper
shape directly.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.fast]


def test_synthetic_atr_emits_classification_shape() -> None:
    from target_workspace.plugins.sources.synthetic_atr import (
        SyntheticAtrSource,
        generate_event,
    )

    src = SyntheticAtrSource()
    assert src.name == "synthetic_atr"

    raw = generate_event(rng_seed=42)
    # Has the basic Target fields
    assert "name" in raw
    assert "lat" in raw
    assert "lon" in raw
    assert "confidence" in raw
    # And the classification sub-dict per tw-x93 convention
    cls = raw["custom_fields"]["classification"]
    assert "model_id" in cls
    assert "class_label" in cls
    assert "taxonomy" in cls
    assert "confidence" in cls
    assert "bounding_box_pixel" in cls
    assert "alternates" in cls
    assert isinstance(cls["alternates"], list)


def test_normalize_passes_payload_through() -> None:
    """The synthetic generator already returns canonical Target-shape
    dicts; normalize() is a no-op identity."""
    from target_workspace.plugins.sources.synthetic_atr import (
        SyntheticAtrSource,
    )

    src = SyntheticAtrSource()
    payload = {"name": "X", "lat": 0.0, "lon": 0.0}
    result = src.normalize(payload, normalization_map={})
    assert result == payload


def test_generate_event_is_deterministic_with_seed() -> None:
    from target_workspace.plugins.sources.synthetic_atr import (
        generate_event,
    )

    a = generate_event(rng_seed=7)
    b = generate_event(rng_seed=7)
    assert a == b


def test_confidence_in_unit_interval() -> None:
    from target_workspace.plugins.sources.synthetic_atr import (
        generate_event,
    )

    for seed in range(10):
        ev = generate_event(rng_seed=seed)
        assert 0.0 <= ev["confidence"] <= 1.0
        cls = ev["custom_fields"]["classification"]
        assert 0.0 <= cls["confidence"] <= 1.0
        for alt in cls["alternates"]:
            assert 0.0 <= alt["confidence"] <= 1.0
