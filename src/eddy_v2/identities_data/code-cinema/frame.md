---
version: v5
name: Code Cinema
chrome: ide
chrome_label: "eddy — pipeline.ts"
tagline: >
  IDE-native — the code is the subject. A pixel-credible VS Code / terminal world: a persistent
  terminal that holds while its output cycles, a config file that flies INTO it, disciplined
  syntax-token colour inside every surface, one VS Code blue as the only voltage.
when_to_pick: >
  Technical / developer content where the screen is code, a terminal, or a config. The persistent
  terminal (device_showcase) is the hero — a config card hands off into it and it runs the result;
  a takeover panel lists what fights you. Best default for tooling, AI-coding, proxy, and setup videos.
grounded_in:
  - registry/blocks/code-diff
  - registry/blocks/code-typing
  - registry/blocks/code-snippet-dark-modern
  - VS Code Dark+ token palette (keyword / string / comment / number / function)
colors:
  ground: "#161616"
  editor: "#1e1e1e"
  panel: "#252526"
  panel-edge: "#333333"
  accent: "#4fc1ff"
  text: "#d4d4d4"
  muted: "#808080"
  kw: "#569cd6"
  str: "#ce9178"
  cmt: "#6a9955"
  num: "#b5cea8"
  fn: "#dcdcaa"
fonts:
  display: "JetBrains Mono"
  mono: "JetBrains Mono"
  body: "JetBrains Mono"
signature_archetypes:
  - device_showcase
  - card_handoff
  - panel_takeover
  - type_slam
  - lower_third
motion:
  preset: snappy
  transition_default: push_slide
  seam_palette: [push_slide, wipe_handoff, crossfade]
  character: >
    Type-on and snap-to-grid. The terminal window arrives once and HOLDS while its output cycles
    (internal seams crossfade so the chrome never moves); a config card flies INTO the window and the
    window runs it, printing result rows as consequences; the accent rule draws left→right like a
    cursor selection sweep; the takeover panel pushes in. Entrances power3/power4.out ~0.34s, exits
    faster (power3.in, blur). One ambient breath on the hold. Nothing drifts.
icon:
  stroke: 2.0
  draw: true
---

# Code Cinema — frame spec

The unit is the frame (1920×1080; a 9:16 variant is documented below). Atoms are sacred: a #161616
stage under a #1e1e1e editor, #252526 panels on #333 hairlines, ONE VS Code blue (`#4fc1ff`) that
behaves like a prompt/cursor, and JetBrains Mono at every size. The monoculture IS the identity —
never pair a second family.

## Colors
- `ground #161616` — the stage behind the editor (never painted in overlay mode).
- `editor #1e1e1e` — the editor / terminal surface; the window the viewer reads.
- `panel #252526` on a `panel-edge #333333` 1px hairline — titlebars, tabs, chips. Borders over shadows.
- `accent #4fc1ff` — the single VS Code blue: prompt `$`, kicker, active-tab underline, CTA, cursor.
  It draws and lights; it never fills large areas.
- `text #d4d4d4` / `muted #808080`.
- Syntax tokens — used ONLY inside a code/terminal surface (realism, never decoration): keyword
  `#569cd6`, string / config-value `#ce9178`, comment / success-tick `#6a9955`, number `#b5cea8`,
  function / filename `#dcdcaa`.

## Typography
JetBrains Mono only (bundled — embeds with no network). Weight contrast: 400/600 for labels and rows,
800 for headline numbers and slams. `tabular-nums` on all data. Uppercase micro-labels with 0.2em
tracking read as terminal chrome. The mono is display and body both.

## Motion (character: snappy)
Type-on, snap-to-grid, cursor-sweep. The terminal enters once (power3.out) and holds; content cycles
inside it with forced crossfades so the window never jumps. A config card reads at frame-left, then
flies INTO the terminal (long travel, shrinks — relinquishes frame authority) and the terminal runs
it: a spinner spins, then result rows print as consequences. The accent rule draws left→right like a
selection sweep. Exits are faster than entrances (power3.in, blur). One ambient breath on the hold.

## Components
- **device_showcase (HERO)** — a pixel-credible terminal: titlebar with macOS traffic-light dots, a
  `$` prompt in accent, mono command rows, dim `#808080` output, green `#6a9955` success ticks. It
  PERSISTS across consecutive beats sharing a `surface`; only the inner content cross-fades.
- **card_handoff** — a `config.toml` file-card (mono, filename in `#dcdcaa`, value in `#ce9178`) that
  flies INTO the persistent terminal; the window prints the translated result rows.
- **panel_takeover** — a full-frame IDE list (accent tick + hairline index chip) of what fights you.
- **type_slam** — a mono headline with one keyword lit in accent, the rule sweeping under it.
- **overlay: ide-panel** — a compact rounded plate with a three-dot titlebar (dots painted via radial
  gradients, not shadows), pinned in the left safe zone; carries a lower-third, a stat, or a proxy
  window. Annotates the screen recording; never covers the code the viewer must read.

## Frame treatments
- **Cover / hook**: type_slam or kinetic title in mono, accent rule sweeping under it, a faint `// KEYWORD`
  ghost drifting behind, one accent glow bloom off the top-left. Fill the frame, left-aligned like code.
- **Stat**: a jumbo mono numeral counting up (`tabular-nums`), accent-lit.
- **Cutaway code**: the persistent terminal running the real command, syntax-lit.

## Aspect-ratio behaviour
16:9 primary. 9:16 (Shorts): the terminal spans the upper third as a hook card; the accent rule and
prompt scale up; safe-zone becomes top-anchored so burned captions clear the lower third.

## Numerals & claims
Never invent figures. Numbers come from the transcript. Render an unknown as `—`.

## Negative list (enforced by the engine + rubric)
No box-shadows (hairlines carry every edge), no rainbow / multi-hue linear gradients as decoration,
no conic gradients, no orb divs, no hue-rotate, no second font family, no purple→blue AI gradients,
no bokeh / particle fields, no `--veil-bg`. Syntax-token colour is allowed ONLY inside a code/terminal
surface.
