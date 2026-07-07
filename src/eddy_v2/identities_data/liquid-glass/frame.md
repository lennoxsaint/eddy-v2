---
version: v5
name: Liquid Glass
chrome: glass
chrome_label: "EDDY"
tagline: >
  Apple WWDC dark-glass product cinema — a near-black keynote stage, one cool Apple-system-cyan
  accent, and translucent glass panels that read as real material (backdrop blur, a specular
  top-lit → bottom-dark edge, a subtle inner top highlight). Calm, expensive, connected.
when_to_pick: >
  Product and app moments that must feel expensive and calm — the reveal, a feature showcase, a
  device running locally. The device_showcase is the hero: a frosted-glass panel whose spec rows
  print value-right in cyan; a counter counts up under a cyan glow; the CTA is a frosted accent
  button the cursor tip lands ON. Best for showing an app (e.g. Threadify) with keynote restraint.
grounded_in:
  - registry/blocks/ios26-liquid-glass
  - registry/blocks/liquid-glass-widgets
  - registry/blocks/vfx-iphone-device
  - Apple keynote product cinema (dark stage, one accent, specular glass)
colors:
  ground: "#050507"
  stage-bg: "#050507"
  accent: "#5AC8FA"
  accent2: "#2b6b86"
  text: "#f5f7fa"
  muted: "#868fa0"
  glass-fill: "rgba(255,255,255,0.055)"
  hairline: "rgba(255,255,255,0.10)"
fonts:
  display: "Inter Variable"
  mono: "SF Mono"
  body: "Inter Variable"
signature_archetypes:
  - device_showcase
  - counter_scale
  - cursor_press
  - kinetic_title
  - lower_third
motion:
  preset: luxe
  transition_default: crossfade
  seam_palette: [crossfade, zoom_through, push_slide]
  character: >
    Slow, weighted, cinematic. Entrances arrive from a soft blur (power3.out ~0.5s) and settle; the
    glass panel holds while its spec rows print as consequences; the accent rule draws left→right; a
    single specular sweep passes across the frost once and does not loop; a faint cool aurora blooms
    and breathes behind the near-black stage. The cursor travels and its arrival IS the press — the
    pill pops once on back.out (the only overshoot in the whole render), the cyan glow blooms FROM
    the press. Nothing is fast; nothing is loud; nothing drifts without cause.
icon:
  stroke: 1.6
  draw: true
---

# Liquid Glass — frame spec

The unit is the frame (1920×1080; a 9:16 variant is documented below). Atoms are sacred: a near-black
keynote stage (`#050507`), ONE cool Apple-system-cyan accent (`#5AC8FA`), translucent glass panels
with a specular edge, light-weight SF-like display type, and mono chrome for data. Depth is flat-plane:
hairlines + a faint cool aurora bloom + vignette + grain — never a rainbow gradient, never an orb field.

## Colors
- `ground / stage-bg #050507` — the keynote stage, near-black and flat. Depth is painted by glow
  layers, not by a gradient background.
- `accent #5AC8FA` — the single Apple system cyan: kicker, prompt, spec value, CTA edge, cursor. It
  lights and edges; it never fills a large area.
- `accent2 #2b6b86` — a deep cyan-slate in the SAME hue family, used only for the faint aurora bloom.
- `text #f5f7fa` near-white / `muted #868fa0` cool grey.
- Glass: `glass-fill rgba(255,255,255,0.055)` on a `hairline rgba(255,255,255,0.10)` 1px edge, with an
  inset top specular (`rgba(255,255,255,0.26)`) and an inset bottom-dark edge (`rgba(0,0,0,0.38)`).

## Typography
- Display: **Inter Variable** (SF-like) — 200/300 for the large calm headlines and the counter, 500
  for the one lit word and labels. Light weight is the whole voice; never go heavy.
- Data / chrome: **SF Mono** with `tabular-nums` on the counter and every spec value.
- Weight contrast is 200↔500 (calm, not loud). One sans, one mono; never a serif, never a second sans.

## Motion (character: luxe)
Slow and weighted. Entrances from a soft blur (power3.out ~0.5s), then settle. The glass device panel
holds while its spec rows print value-right in cyan as consequences; the accent rule draws left→right
like a selection sweep; ONE specular sweep passes across the frost and stops. A faint cool aurora
breathes behind the stage; the vignette settles then breathes once. The CTA cursor travels ~0.8s and
its arrival time IS the press — the pill pops once on `back.out` (the only overshoot in the render) and
the cyan glow blooms FROM the press, not before it. Exits are unhurried but faster than entrances.

## Components
- **device_showcase (HERO)** — a frosted-glass product panel: a titlebar with macOS traffic-light
  dots, a subtle inner top sheen, and spec rows that print `key … value` with the value right-aligned
  in cyan and a hairline between rows. It reads as a real pane of glass, not a gray card.
- **counter_scale** — one calm jumbo numeral (weight 200, `tabular-nums`) counting up under a cyan
  glow envelope; a label and a drawn accent rule beneath it.
- **cursor_press** — a frosted cyan accent button; the cursor tip lands ON the pill and presses it
  (the one `back.out` pop), the glow blooming as the consequence.
- **kinetic_title** — a light SF headline with one word lit cyan; a single shimmer crosses the line;
  the accent rule sweeps under it.
- **lower_third** — a compact frosted glass pill (specular edge, cyan micro-label) pinned in the safe
  zone; annotates the frame without fighting the talking head.
- **overlay: glass-plate** — a compact translucent plate (true alpha, blur + specular inset) in the
  left safe zone carrying any of the above; the chrome pane-stack is never painted in overlay.

## Frame treatments
- **Reveal**: a light headline resolves from blur over the near-black stage, a shimmer crosses, a cool
  aurora breathes behind. Calm and expensive.
- **App showcase**: the frosted device panel holds while its spec rows print; the panel is the subject.

## Aspect-ratio behaviour
16:9 primary. 9:16 (Shorts): the glass panel spans the upper third; the counter and headline scale up;
the safe zone becomes top-anchored so burned captions clear the lower third.

## Numerals & claims
Never invent figures. Numbers come from the transcript. Render an unknown as `—`.

## Negative list (enforced by the engine + rubric)
No box-shadows EXCEPT material-honest INSET specular on glass (the one sanctioned exception); no drop
shadows anywhere. No rainbow / multi-hue linear gradients as decoration, no conic gradients, no orb
divs (the five glass-orb rules are purged — the divs collapse to nothing), no hue-rotate, no second
sans font, no serif, no purple→blue AI gradients, no bokeh / particle fields, no looping breathe, no
`--veil-bg`. Only `--vignette-color` and `--shimmer` survive from the finishing layer. One cool accent
only; at most two glass panels per scene; one finite specular sweep.
