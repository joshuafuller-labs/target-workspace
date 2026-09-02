// MIL-STD-2525-aligned CoT type taxonomy — a curated subset, not the
// full standard. Most boards use ~25-30 of the hundreds of possible
// codes; this set covers them. Free-text mode (CotTypePicker advanced
// toggle) is still available for the rare bird.
//
// CoT type strings concatenate single-character codes with dashes:
//   a-{affiliation}-{dimension}[-{function}[-{modifier}]]
//
// e.g. a-h-G-E-V-C  →  hostile / ground / equipment / vehicle / civilian
//
// We model each step as { code, label, hint } and let downstream
// dimensions/functions/modifiers depend on prior choices.

export interface Choice {
  code: string;
  label: string;
  hint?: string;
}

export const AFFILIATIONS: readonly Choice[] = [
  { code: "h", label: "Hostile", hint: "Confirmed adversary" },
  { code: "s", label: "Suspect", hint: "Probable adversary, not yet confirmed" },
  { code: "u", label: "Unknown", hint: "Insufficient data to classify" },
  { code: "p", label: "Pending", hint: "Awaiting evaluation" },
  { code: "f", label: "Friend", hint: "Friendly force" },
  { code: "n", label: "Neutral", hint: "Non-combatant" },
  { code: "j", label: "Joker", hint: "Friendly acting as hostile (exercise)" },
  { code: "k", label: "Faker", hint: "Friendly acting as hostile (deception)" },
] as const;

export const DIMENSIONS: readonly Choice[] = [
  { code: "G", label: "Ground", hint: "Surface forces / equipment" },
  { code: "A", label: "Air", hint: "Airborne contacts" },
  { code: "S", label: "Sea surface", hint: "Surface naval / maritime" },
  { code: "U", label: "Subsurface", hint: "Submerged / undersea" },
  { code: "P", label: "Space", hint: "Orbital / launch" },
  { code: "F", label: "SOF", hint: "Special operations / forces" },
] as const;

/** Function codes per dimension. The label and hint are dimension-aware. */
export const FUNCTIONS: Record<string, readonly Choice[]> = {
  G: [
    { code: "U", label: "Unit / Person", hint: "Personnel, formation, dismounts" },
    { code: "E", label: "Equipment", hint: "Vehicles, weapon systems, sensors" },
    { code: "I", label: "Installation", hint: "Fixed site, building, depot" },
  ],
  A: [
    { code: "F", label: "Fixed-wing", hint: "Jet, prop, fighter, cargo" },
    { code: "H", label: "Rotary-wing", hint: "Helicopter" },
    { code: "M", label: "UAV / UAS", hint: "Drone, loitering munition" },
    { code: "T", label: "Track", hint: "Generic air track" },
  ],
  S: [
    { code: "C", label: "Combatant", hint: "Surface combatant ship" },
    { code: "X", label: "Auxiliary", hint: "Support, supply, civilian" },
  ],
  U: [{ code: "S", label: "Submarine", hint: "Submerged vessel" }],
  P: [
    { code: "V", label: "Vehicle", hint: "Satellite / launcher" },
    { code: "L", label: "Launch", hint: "Active launch event" },
  ],
  F: [
    { code: "U", label: "SOF unit", hint: "SOF personnel" },
    { code: "E", label: "SOF equipment", hint: "SOF platform" },
  ],
};

/** Modifier codes per (dimension, function). Empty list = no modifier
 *  pickable; full CoT is the 3-segment prefix.  */
export const MODIFIERS: Record<string, readonly Choice[]> = {
  "G/E": [
    { code: "V", label: "Vehicle", hint: "Wheeled or tracked vehicle" },
    { code: "VC", label: "Vehicle • Civilian", hint: "Civilian / commercial vehicle (technical)" },
    { code: "VM", label: "Vehicle • Military", hint: "Military vehicle" },
    { code: "WT", label: "Wheeled • Towed", hint: "Towed weapon system (artillery)" },
    { code: "WMS", label: "Missile/MRL", hint: "Surface-to-surface / MRL" },
    { code: "WAS", label: "SAM", hint: "Surface-to-air missile" },
  ],
  "G/U": [
    { code: "C", label: "Civilian", hint: "Civilian person / dismount" },
    { code: "M", label: "Militant", hint: "Combatant on foot" },
  ],
  "G/I": [
    { code: "B", label: "Building", hint: "Fixed structure" },
    { code: "S", label: "Site", hint: "Compound / facility" },
  ],
  "A/F": [
    { code: "F", label: "Fighter", hint: "Combat aircraft" },
    { code: "C", label: "Cargo", hint: "Transport" },
    { code: "B", label: "Bomber", hint: "Strategic / tactical bomber" },
  ],
  "A/M": [
    { code: "F", label: "Fixed-wing UAV", hint: "Recon / strike fixed-wing drone" },
    { code: "R", label: "Rotary UAV", hint: "Quad / hex copter" },
    { code: "L", label: "Loitering munition", hint: "One-way attack drone" },
  ],
  "S/C": [
    { code: "S", label: "Combatant ship", hint: "Frigate, destroyer, cruiser" },
    { code: "B", label: "Boat", hint: "Patrol, fast attack" },
  ],
};

/** Build the dash-joined CoT string from picker state. Trailing empty
 *  segments are omitted so a partial selection yields a valid prefix
 *  (e.g. `a-h` is a legal type meaning "hostile, dimension TBD"). */
export function buildCotType(
  affiliation: string,
  dimension: string,
  fn: string,
  modifier: string,
): string {
  const parts = ["a", affiliation, dimension, fn];
  if (modifier) {
    for (const seg of modifier.split("/")) {
      parts.push(seg);
    }
  }
  while (parts.length > 2 && !parts[parts.length - 1]) parts.pop();
  return parts.join("-");
}

/** Reverse: parse a CoT type back into picker fields. Best-effort —
 *  unknown codes round-trip into the advanced/free-text mode. */
export function parseCotType(
  cot: string,
): { affiliation: string; dimension: string; fn: string; modifier: string } {
  const segs = cot.split("-");
  // segs[0] is the 'a' atom prefix; we don't surface other atoms here.
  const affiliation = segs[1] ?? "";
  const dimension = segs[2] ?? "";
  const fn = segs[3] ?? "";
  const modifier = segs.slice(4).join("/");
  return { affiliation, dimension, fn, modifier };
}
