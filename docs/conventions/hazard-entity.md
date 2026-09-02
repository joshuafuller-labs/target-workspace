# Hazard entity convention

`tw-49a`. A *soft* convention for the period before entity-type pluralism (`tw-auf`) lands a first-class `entity_kind` column.

## Rationale

Disaster operations need to distinguish *contacts you're trying to reach* (persons, vehicles, units) from *obstacles in the way* (flooded roads, downed lines, gas leaks, debris). Both live on the same kanban / map today, but a rescue boat icon next to a flooded-road icon next to a victim icon adds cognitive load every time the IC scans the map. Hazards belong visually distinct so "why can't we get there?" is one glance.

## Convention

A target carries `custom_fields.entity_kind = "hazard"` when it represents a dynamic obstacle. The SPA reads that flag and renders:

- **Card**: a red `⚠ HAZARD` chip in the metadata row.
- **Map**: red color, slightly thicker label, no green hostile/friend semantics; the point glyph picks up a fixed warning palette regardless of `cot_type`.

The convention also acts as a hint to the (future) routing engine that this point should be *avoided* when computing dispatch.

Backend has no schema awareness today — the flag round-trips through `custom_fields` like any other dictionary entry. When `tw-auf` lands, `entity_kind` becomes a first-class column and this doc gets retired with a migration that hoists existing `custom_fields.entity_kind` values into the column.

## Allowed values (today)

- `"hazard"` — barricaded, dangerous, or obstructing
- (future) `"resource"`, `"task"`, `"contact"` once pluralism lands

Anything else: don't set the field; the default contact treatment applies.

## Example payload

```json
{
  "name": "Flooded · FM 1340 / S Fork",
  "lat": 30.0598,
  "lon": -99.3210,
  "cot_type": "a-u-G-I",
  "custom_fields": {
    "entity_kind": "hazard",
    "address": "FM 1340 at S Fork Guadalupe",
    "water_over_road_m": 1.8,
    "reporter": "passing motorist"
  }
}
```

This card renders the `⚠ HAZARD` chip on the kanban and a red glyph on the map; routing-aware dispatch (post-MVP) treats the lat/lon as a blocking polygon to avoid.
