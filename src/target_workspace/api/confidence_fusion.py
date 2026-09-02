"""Independent-source confidence fusion (tw-a9a).

When N independent cues all assert the same physical target, the
combined probability that the assertion is correct is:

    aggregate = 1 - prod(1 - c_i)

Ukraine fires-targeting playbook (`docs/research/ukraine-fires-targeting.md`)
calls this out explicitly: 3 cues at 0.7/0.7/0.5 produce 0.955, not
the highest single 0.7. The track-correlation engine writes the
breakdown into `target.custom_fields.confidence_chain`.

Independence is an assumption — it's *the* assumption the operator
makes when they cite three sources. If two cues are correlated (same
sensor, same analyst, same upstream feed) the aggregate is wrong-
optimistic. That's a problem for source curation, not for this math.
"""

from __future__ import annotations

from collections.abc import Iterable


def fuse(values: Iterable[float | None]) -> float | None:
    """Aggregate independent confidences. Returns None for an empty / all-None list."""
    cleaned: list[float] = []
    for v in values:
        if v is None:
            continue
        c = max(0.0, min(1.0, float(v)))
        cleaned.append(c)
    if not cleaned:
        return None
    not_p = 1.0
    for c in cleaned:
        not_p *= 1.0 - c
    return 1.0 - not_p
