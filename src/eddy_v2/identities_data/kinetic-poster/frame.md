---
version: v5
name: Kinetic Poster
chrome: poster
chrome_label: "EDDY CUT"
tagline: >
  Beat-grid typographic FORCE — a Swiss/kinetic poster where type is the subject. Near-black ground,
  off-white ink, ONE signal-red voltage used sparingly. Massive lowercase Archivo Black slabs on a
  flat plane (hairlines + a single accent glow + vignette + grain), keyed to a 124-bpm beat grid.
when_to_pick: >
  Hooks, big claims, jaw-drop numbers, punchy flips, Shorts. Maximum stopping power without shadows or
  gradients: oversized lowercase type that slams on the beat, a hard editorial strike-swap, count-ups
  that own the frame, a single red accent. Use for the opening 8 seconds, a stat, or a sharp flip.
grounded_in:
  - registry/examples/kinetic-type
  - registry/components/caption-kinetic-slam
  - Swiss International Typographic Style (grid, flat colour fields, one accent)
colors:
  ground: "#0b0b0d"
  panel: "#141416"
  panel-edge: "#26262a"
  accent: "#FF2D2D"
  ink: "#0b0b0d"
  text: "#f5f3ee"
  muted: "#8a8a92"
fonts:
  display: "Archivo Black"
  mono: "Space Mono"
  body: "Archivo Black"
signature_archetypes:
  - type_slam
  - counter_scale
  - strike_swap
  - lower_third
motion:
  preset: snappy
  transition_default: push_slide
  seam_palette: [zoom_through, squeeze, push_slide, cut]
  bpm: 124
  character: >
    Slam-to-grid on the beat. Type arrives fast and heavy (power4.out ~0.34s), each line slamming on
    its own beat; the lit key word glow-envelopes AFTER its line lands; the accent rule sweeps in
    left→right; numbers count up hard, then the number glow-envelopes as it settles. The strike bar
    physically sweeps the old word, THEN the new word snaps in accent — a consequence, not a
    co-occurrence. Seams hit on the beat and never repeat a neighbour (zoom_through / squeeze /
    push_slide / cut). Exits are faster than entrances (power3.in). One ambient breath on the hold.
icon:
  stroke: 2.4
  draw: true
---

# Kinetic Poster — frame spec

The unit is the frame (1920×1080; 9:16 is a native home for this identity). Atoms are sacred: a
near-black ground (`#0b0b0d`, tinted off pure black), one signal-red voltage (`#FF2D2D`), off-white
ink (`#f5f3ee`), Archivo Black at poster scale, Space Mono for chrome. FLAT colour fields only — the
poster convention here is hard flat fields and hairlines, NOT the offset drop-shadow of the old v4.

## Colors
- `ground #0b0b0d` (not pure black) / `panel #141416` slab on a `panel-edge #26262a` 1px hairline.
- `accent #FF2D2D` signal red — the single voltage: the lit key word, the number, the rule, a punch
  field. It fills small hard fields and lights key type; it never becomes a gradient or a glow-shadow.
- `ink #0b0b0d` — the type that sits ON an accent field (punch register, lower-third, key highlight).
- `text #f5f3ee` off-white display ink / `muted #8a8a92` struck + secondary chrome.

## Typography
- Display: **Archivo Black** (bundled, 400 only) — poster weight at 60–340px, **lowercase**, tight
  negative tracking (−0.02 to −0.03em). This face IS the punch.
- Chrome / mono: **Space Mono** (bundled), uppercase, wide tracking — the "no. 01" index label, the
  marquee, the side label. Never a second sans family.
- Extreme scale contrast: a tiny mono index over a giant lowercase slab. Numerals `tabular-nums`.

## Registers
- **Default (dark)**: off-white ink on near-black, one key word / number lit red.
- **Punch (`reg-punch`)**: one scene flips to a red FIELD with ink type — the loudest beat. Used
  sparingly (the equivalent of the gold's fire register), never two in a row.

## Motion (character: snappy, beat-grid 124 bpm)
Slam-to-grid. Lines slam on the beat (power4.out); the key word glow-envelopes AFTER it lands; the
accent rule sweeps left→right; count-ups run hard then glow-settle. The strike bar sweeps the old
word, THEN the new word snaps accent (physical cause → effect). Seams hit on the beat and never
repeat the neighbour. Exits whip faster than entrances (power3.in). One ambient breath on the hold.

## Components
- **type_slam** — massive lowercase slabs; one key word lit on a red field, the rule sweeping under.
- **counter_scale** — a jumbo red numeral counting up, a lowercase label, an accent rule.
- **strike_swap** — a hard editorial bar strikes the old (muted) word; the new word snaps in red.
- **lower_third** — a flat red chip with ink type + an ink icon-coin.
- **overlay: poster chip** — the same archetypes, compact, choreographed to the same bar inside the
  left safe zone (true alpha, no full-frame paint); the beat grid holds.

## Frame treatments
- **Hook**: a giant lowercase Archivo Black slab, one red key word, the accent rule sweeping under,
  a faint ghost keyword drifting behind, one blurred red glow off the top-left. Fill the frame.
- **Big number**: one jumbo red count-up, a lowercase label, the rule under it.
- **Flip**: strike_swap — the bar sweeps, the accent word lands.

## Chrome furniture
Edge-to-edge poster marquees (top solid, bottom outline) on 1px red rules, corner crop marks, a
slow-spinning red burst, a rotated mono side label. The "no. 01" mono index is the kicker on every
scene. All furniture is flat — hairlines and flat fields, never a shadow.

## Aspect-ratio behaviour
9:16 primary for this identity (Shorts). 16:9: the slab pins to the safe zone; type scales up. In
9:16 the slab spans the upper third as a hook card clear of burned captions.

## Numerals & claims
Never invent figures — a loud wrong number is worse than a quiet one. Numbers come from the
transcript. Render an unknown as `—`.

## Negative list (enforced by the engine + rubric)
No box-shadows and no text-shadows (the old v4 offset shadow is GONE — hairlines + flat fields carry
every edge), no rainbow / multi-hue linear gradients as decoration, no conic gradients, no orb divs,
no hue-rotate, no `--veil-bg`, no second sans family, no purple→blue AI gradients, no bokeh / particle
fields, no fonts.googleapis. The single-hue accent stripe field and the accent glow are the only
non-flat texture, and both read as poster material, not decoration.
