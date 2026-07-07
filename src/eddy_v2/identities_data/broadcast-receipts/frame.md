---
version: v5
name: Broadcast Receipts
chrome: broadcast
chrome_label: "RECEIPTS"
tagline: >
  Creator social-proof newsroom — the receipts PRINT and accumulate. Thermal receipts feed out of
  the printer on cream paper (perforated teeth, a drawn red underline under the figure, a "RECEIPTS .
  NOT PROMISES" foot), credible platform post cards carry the real proof, and a match ledger fills up
  row by row inside a live broadcast package. One broadcast red is the only voltage.
when_to_pick: >
  Receipts-first storytelling: a real post (yours or a plagiarist's), a match ledger, a milestone, a
  verdict. Cutaways print thermal receipts and stack platform post cards inside the broadcast package
  (bug + ticking clock + data ticker); overlays are clean TV lower-thirds and receipt slips in the
  safe zone. The credibility-and-community identity — proof over promises.
grounded_in:
  - registry/blocks/yt-lower-third
  - registry/blocks/x-post
  - registry/blocks/receipt-thermal
  - registry/blocks/macos-notification
colors:
  ground: "#0d0d0f"
  panel: "#17171a"
  panel-edge: "#2a2a2e"
  accent: "#e5372f"
  text: "#f3f1ec"
  muted: "#8a8781"
  paper: "#fdfaf1"
  ink: "#16140f"
fonts:
  display: "Montserrat"
  mono: "IBM Plex Mono"
  body: "Montserrat"
signature_archetypes:
  - receipt_print
  - social_post
  - ledger
  - counter_scale
  - lower_third
motion:
  preset: snappy
  transition_default: wipe_handoff
  seam_palette: [wipe_handoff, push_slide, crossfade]
  character: >
    Broadcast-crisp and physical. A receipt feeds out of the printer top→bottom (clip-path inset) and
    the red underline draws under the key figure as a CONSEQUENCE of the print finishing; the next
    receipt wipes in on the same edge and the earlier evidence stays. A platform post card snaps in
    and its metrics count up. The match ledger appends rows that PERSIST — the list fills up, it never
    resets. The tally counter counts up while its rule sweeps left→right. Entrances power3/power4.out
    ~0.34s, exits faster (power3.in, blur). One ambient breath on the hold; the clock ticks and the
    ticker crawls. Nothing drifts, nothing floats.
icon:
  stroke: 2.0
  draw: true
---

# Broadcast Receipts — frame spec

The unit is the frame (1920×1080; a 9:16 variant is documented below). Atoms are sacred: a dark
newsroom stage (`#0d0d0f`) under a live broadcast package, thermal receipts on cream paper, credible
dark post cards on `#2a2a2e` hairlines, ONE broadcast red (`#e5372f`) that lights the verdict, the
underline, and the kickers, and Montserrat display over IBM Plex Mono chrome. Receipts print and
accumulate — proof over promises.

## Colors
- `ground #0d0d0f` — the dark newsroom stage (never painted in overlay mode).
- `panel #17171a` on a `panel-edge #2a2a2e` 1px hairline — post cards, lower-thirds, chrome plates.
  Borders over shadows, everywhere.
- `accent #e5372f` — the single broadcast red: bug dot, kicker, receipt underline, ledger ticks,
  verdict figure, CTA. It draws and lights; it never fills large flat areas as decoration.
- `text #f3f1ec` / `muted #8a8781`.
- `paper #fdfaf1` cream thermal receipt with `ink #16140f` — the receipt is mono, dashed, perforated.

## Typography
- Display: **Montserrat** (bundled) — 800 for names/headlines/figures, 500 for post body. Newsroom-clean.
- Chrome / handles / metrics / receipts: **IBM Plex Mono** (bundled) with `tabular-nums`, uppercase
  micro-labels tracked 0.2em read as broadcast chrome. Thermal receipts are mono end to end.
- ONE sans + one mono; never a serif, never a second sans. ONE register per scene.

## Motion (character: snappy)
Broadcast-crisp, physical, connected. The receipt feeds out of the printer (clip-path top→bottom) and
the red underline draws under the figure as a consequence of the print completing. The next receipt
wipes in on the same edge; earlier receipts stay on screen as evidence. Post-card metrics count up on
snap-in. The ledger appends rows that persist — it fills up, never resets. Exits are faster than
entrances (power3.in, blur). One ambient breath on the hold; the clock ticks, the data ticker crawls.

## Components
- **receipt_print (HERO)** — a thermal receipt on cream paper: perforated clip-path teeth, dashed
  rules, a mono figure with a drawn red underline, a `RECEIPTS · NOT PROMISES` foot. It PRINTS
  top→bottom and stacks — evidence that accumulates.
- **social_post (HERO)** — a credible platform post card: monogram avatar, name, `@handle`, red
  verified badge, body, and like/repost/view metrics that count up. The screenshot IS the proof.
- **ledger** — the match list that fills up: red-tick rows with a right-aligned red verdict value,
  appended one beat at a time and held on screen.
- **counter_scale** — the tally figure in red, counting up while the accent rule sweeps under it.
- **lower_third** — a TV lower-third (red left bar + mono label + name) naming what's on screen.
- **overlay: newsroom plate** — a compact dark plate on a hairline pinned in the left safe zone;
  carries a lower-third, a receipt slip, or a stat. Never covers the talking head's eye-line.

## Frame treatments
- **Receipt reveal**: the dark newsroom, a thermal receipt feeding out, the figure underlined in red,
  the mono foot printing last. Stack a second receipt on the same edge for the compounding proof.
- **Verdict**: the final receipt reads the verdict; the red underline lands under it as the consequence.

## Aspect-ratio behaviour
16:9 primary. 9:16 (Shorts): the receipt / post card centres and scales, the bug and ticker pin to
the top and bottom safe bands, and captions clear the lower third.

## Numerals & claims
Never invent figures or fabricate a post — the whole identity is credibility. Metrics come from the
transcript/screen; an unknown renders as an em-dash slot.

## Negative list (enforced by the engine + rubric)
No box-shadows (hairlines carry every edge), no rainbow / multi-hue linear gradients as decoration,
no conic gradients, no orb divs, no hue-rotate, no second sans font, no purple→blue AI gradients, no
bokeh / particle fields, no `--veil-bg`. The single-hue accent→edge frameline and the accent radial
glow are the only gradients, and they light rather than decorate.
