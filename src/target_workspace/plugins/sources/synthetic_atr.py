"""Synthetic AI-ATR Source — reference plugin for target.classification.

First-party example for plugin authors building real ATR (automatic
target recognition) integrations like Saker Scout. Emits Target-shaped
dicts already populated with the custom_fields.classification convention
from tw-x93, so a downstream visualizer can prove the round-trip works
without a real model in the loop.

generate_event(rng_seed) is the demo helper — scenarios / fixtures
invoke it on a cadence to feed the pipeline. The class itself is a
no-op normalizer since the helper already returns canonical shape.
"""

from __future__ import annotations

import random
from typing import Any

from target_workspace.plugins.loader import register_source

_TAXONOMY = "mil-vehicle-v1"
_CLASSES = [
    "tank",
    "apc",
    "truck",
    "jeep",
    "pickup",
    "motorcycle",
    "infantry",
    "uav",
]


class SyntheticAtrSource:
    name = "synthetic_atr"

    def normalize(
        self,
        payload: dict[str, Any],
        normalization_map: dict[str, Any],
    ) -> dict[str, Any]:
        _ = normalization_map
        return payload


def generate_event(rng_seed: int) -> dict[str, Any]:
    """Produce a Target-shaped dict with a populated classification block.

    Deterministic given rng_seed so tests and scenarios are repeatable.
    """
    rng = random.Random(rng_seed)  # noqa: S311 — synthetic scenario data, deterministic by seed; not security-sensitive

    primary = rng.choice(_CLASSES)
    primary_conf = round(rng.uniform(0.55, 0.99), 3)

    alt_pool = [c for c in _CLASSES if c != primary]
    rng.shuffle(alt_pool)
    alternates = [
        {"class_label": alt_pool[0], "confidence": round(rng.uniform(0.05, primary_conf), 3)},
        {"class_label": alt_pool[1], "confidence": round(rng.uniform(0.01, primary_conf), 3)},
    ]

    lat = round(rng.uniform(-89.0, 89.0), 6)
    lon = round(rng.uniform(-179.0, 179.0), 6)

    x = rng.randint(0, 1600)
    y = rng.randint(0, 1200)
    w = rng.randint(40, 320)
    h = rng.randint(40, 240)

    return {
        "name": f"ATR-{primary}-{rng_seed}",
        "lat": lat,
        "lon": lon,
        "confidence": primary_conf,
        "custom_fields": {
            "classification": {
                "model_id": "synthetic-atr-v0",
                "class_label": primary,
                "taxonomy": _TAXONOMY,
                "confidence": primary_conf,
                "bounding_box_pixel": {"x": x, "y": y, "w": w, "h": h},
                "alternates": alternates,
            },
        },
    }


register_source(SyntheticAtrSource.name, SyntheticAtrSource)
