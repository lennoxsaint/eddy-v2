---
version: v5
name: Editorial Data
chrome: editorial
chrome_label: "ANALYSIS"
tagline: NYT/Bloomberg data-journalism — Fraunces serif headlines, hairline rules, ink-on-cream, charts that draw themselves.
when_to_pick: >
  Any claim, number, comparison, or trend that needs authority. Cutaways are full-frame data scenes
  (bar/line charts, big numerals, maps) with a real HyperFrames data-chart block or a bespoke SVG
  chart; overlays are compact editorial cards that footnote the talking head. The credible look.
grounded_in:
  - registry/blocks/data-chart
  - registry/examples/nyt-graph
  - registry/examples/swiss-grid
colors:
  ground: "#f4f1ea"
  panel: "#fbf9f4"
  panel-edge: "#d7d0c0"
  accent: "#c1432c"
  accent2: "#1b1712"
  text: "#1b1712"
  muted: "#8a8073"
  warn: "#b8860b"
fonts:
  display: "Fraunces"
  mono: "IBM Plex Mono"
  body: "IBM Plex Mono"
motion:
  preset: smooth
  transition_default: crossfade
  seam_palette: [crossfade, push_slide, wipe_handoff]
  character: >
    Typeset, not animated. Elements settle rather than fly: a headline rises a few px into place, a
    hairline rule draws across, bars stagger up on a baseline, a numeral GROWS as it counts, a ledger
    fills row by row. Quiet velocity-matched seams (crossfade, push, wipe), never the same twice in a
    row. Restraint is the rule.
signature_archetypes:
  - counter_scale
  - ledger
  - metric_bars
  - big_number
icon:
  stroke: 1.6
  draw: true
---

# Editorial Data — frame spec

The unit is the frame (1920×1080; 9:16 documented). Atoms are sacred: a warm parchment ground, deep
ink, a single editorial vermilion deployed sparingly, Fraunces serif for display + IBM Plex Mono for
data and labels, 1px hairline rules as the only border, and no shadows. Numbers come from the script.

## Colors
- `ground #f4f1ea` cream / `panel #fbf9f4` card, on a `panel-edge #d7d0c0` hairline. Borders, never shadows.
- `accent #c1432c` — editorial vermilion; the one warm voltage, used for a rule, a key bar, a lede word.
- `accent2 #1b1712` ink / `text #1b1712` / `muted #8a8073`.

## Typography
- Display: **Fraunces** (self-hosted, SIL OFL) — 800 for headlines and numerals, 400 for lede italics.
  A real serif is the authority signal; every HyperFrames-bundled serif is banned, so it is embedded.
- Data + labels: **IBM Plex Mono** (bundled) with `tabular-nums`; uppercase micro-labels at `0.2em`.
- Extreme weight contrast (Fraunces 400 vs 800). One serif, one mono. Never a second sans.

## Motion (character: smooth)
Typeset restraint. Entrances `power2.out` ~0.5s; a hairline rule draws left→right; bars stagger up
from a baseline; numerals count. One quiet ambient settle on the hold. Exits fade + lift a few px.

## Components
- **overlay: editorial-card** — a cream card with a hairline top rule, a red kicker label, a serif
  headline, pinned in the safe zone. Footnotes the talking head like a lower third in a documentary.
- **cutaway: data scene** — full-frame cream ground; a real `data-chart` block (data-patched to the
  script's numbers) or a bespoke SVG bar/line chart with a serif title and mono value labels.
- **cutaway: numeral** — one jumbo Fraunces numeral counting up, a red rule, a mono caption.

## Frame treatments
- **Cover / lede**: serif headline set large, a red hairline rule beneath, a faint oversized ghost
  numeral behind for depth. Ink on cream. Fill the frame.
- **Chart**: title in serif small-caps, mono axis labels, the key series in vermilion, the rest muted.

## Aspect-ratio behaviour
16:9 primary. 9:16: the editorial card spans the upper third; the serif headline scales up; the chart
stacks vertically with the key bar last so it lands as the payoff.

## Numerals & claims
Never invent figures — the credibility is the whole point. Numbers come from the transcript; an
unknown renders as an em-dash slot.
