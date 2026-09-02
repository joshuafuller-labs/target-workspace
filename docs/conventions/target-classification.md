# Target classification convention for AI/ATR output

Per docs/research/ukraine-fires-targeting.md §3. ATR pipelines (Saker
Scout-style, Anduril Lattice, even FAA AIS) emit structured class
data alongside lat/lon. The Target Workspace data model has
`confidence` first-class; the rest lives in `target.custom_fields`
with no agreed shape.

This convention defines the soft shape so plugins, publishers, and UI
can opt into a consistent schema **without a database migration**.

## Sub-dict location

```
target.custom_fields.classification = { ... }
```

Plugins that produce class data SHOULD write to this key. Plugins
that consume it SHOULD read from this key. Absence is fine — it's a
soft convention, not a contract.

## Schema (target.custom_fields.classification)

```json
{
  "model_id":          "string — opaque identifier of the model that produced this. Example: 'saker-scout-v3.2', 'lattice-vehicle-cls-2024-09'",
  "class_label":       "string — top-1 label, free-form. Example: 'BTR-82A', 'fishing vessel', 'flooded residential structure'",
  "taxonomy":          "string — namespace of class_label. Example: 'mil-std-2525', 'imo-vessel-types', 'fema-pda-categories'",
  "confidence":        "float [0,1] — top-1 confidence. Duplicates target.confidence; both should match unless model output is being aggregated.",
  "bounding_box_pixel": {
    "x": "int",
    "y": "int",
    "w": "int",
    "h": "int",
    "image_w": "int — original image width in pixels (for downstream resize)",
    "image_h": "int — original image height"
  },
  "alternates": [
    {"class_label": "string", "confidence": "float", "taxonomy": "string"}
  ]
}
```

- All fields are optional. A bare `{"class_label": "BTR-82A"}` is
  valid — alternates are just unavailable.
- `bounding_box_pixel` is the model-output frame in image space; for
  pixel→geo mapping you need the original image's geo-ref which
  lives elsewhere (e.g. EXIF on the captured photo, or a sensor
  pose record).
- `alternates` is sorted by confidence descending. Top-1 is the
  one mirrored into `class_label` + `confidence`.

## Example payloads

### Saker Scout-style ATR

```json
{
  "id": "...",
  "name": "BTR-82A south of Kreminna",
  "lat": 49.0123,
  "lon": 38.2456,
  "confidence": 0.92,
  "custom_fields": {
    "classification": {
      "model_id": "saker-scout-v3.2",
      "class_label": "BTR-82A",
      "taxonomy": "mil-std-2525",
      "confidence": 0.92,
      "bounding_box_pixel": {
        "x": 312, "y": 188, "w": 144, "h": 96,
        "image_w": 1920, "image_h": 1080
      },
      "alternates": [
        {"class_label": "BTR-80",  "confidence": 0.06, "taxonomy": "mil-std-2525"},
        {"class_label": "BMP-2",   "confidence": 0.02, "taxonomy": "mil-std-2525"}
      ]
    }
  }
}
```

### FEMA-style damage classification

```json
{
  "id": "...",
  "name": "142 Oak St",
  "lat": 35.6010,
  "lon": -82.5550,
  "confidence": 0.84,
  "custom_fields": {
    "classification": {
      "model_id": "fema-pda-cnn-v1",
      "class_label": "major-damage",
      "taxonomy": "fema-pda-categories",
      "confidence": 0.84,
      "bounding_box_pixel": null,
      "alternates": [
        {"class_label": "minor-damage", "confidence": 0.13},
        {"class_label": "destroyed",    "confidence": 0.03}
      ]
    },
    "damage_assessment": { ... }  // separate convention from tw-fgz
  }
}
```

## Consumer plugins

When a plugin reads `target.custom_fields.classification`, it
SHOULD:

1. Treat the field as optional. Fall back to `target.confidence` +
   `target.name` if absent.
2. Honor the `taxonomy` field — `BTR-82A` in `mil-std-2525` and
   `BTR-82A` in some random taxonomy are different ontology entries
   even though the label string matches.
3. Surface `alternates` in detail views — operators care about the
   confidence gap between top-1 and top-2 ("BTR-82A 92% / BTR-80 6%"
   is high-confidence; "BTR-82A 41% / BTR-80 39%" is the model
   coin-flipping).

## What this does NOT define

- **Image storage**: where the photo lives. Use `tw-bux` `/v1/capture`
  for that.
- **Pixel-to-geo mapping**: requires sensor pose; out of scope.
- **Model registry**: tracking which models are in production. v1.x.
- **Re-classification on schema upgrade**: handled separately.

## Status

This is a SOFT convention. No code enforces it; no migration ships
with it. Plugins are expected to gravitate toward this shape so
cross-plugin handoff works.
