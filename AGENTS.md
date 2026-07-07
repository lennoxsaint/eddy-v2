# AGENTS.md - Eddy V2 operating instructions

Eddy V2 is the public, source-safe rebuild of Eddy:

raw creator footage in -> proof-gated YouTube long edit, quality-gated Shorts, launch kit, and receipts out.

The canonical public repo is `lennoxsaint/eddy-v2`.

This file governs agents working in this repo. Use `/Users/lennoxsaint/eddy` only as a read-only reference
for current-Eddy comparison. Do not mutate, replace, or backport into that repo while working here.

## Read first

1. `EDDY-PLAYBOOK.md` - the V2 editing contract and taste doctrine.
2. `README.md` - install, CLI, MCP, audio proof, proof layers, and bakeoff behavior.
3. `CONTEXT.md` - shared product language.
4. `docs/BAKEOFF.md` and `docs/adr/*.md` - durable decisions.

If guidance conflicts, the latest user instruction wins, then current repo files and receipts, then docs,
then memory or historical notes.

## Hard gates

- Never edit, move, delete, overwrite, or transform raw source media.
- Every output must live under `<source-folder>/eddy-runs/<run-slug>/`.
- Hash sources before and after each run. Treat hash mismatch as a hard blocker.
- Every model call, cloud attempt, ffmpeg command, HyperFrames command, cost, fallback, gate verdict,
  blocker, and ranking decision must land in the run's `receipts.jsonl`.
- Failed renders, samples, corrupt Shorts, and prior replaced finals belong in `quarantine/`, never as
  fresh `final/` deliverables.
- No publish, upload-to-platform, scheduling, or social-send code belongs in Eddy V2.
- Cloud quality APIs are allowed only when configured, fully receipted, and cost-capped. `--local-only`
  must refuse all cloud/model/image/audio egress.
- Do not claim a run is publishable until machine gates pass, Strong Studio Sound or approved cloud parity
  is proven, and Lennox records 8/10+ review scores for long edit, motion, audio, and Shorts.

## V2 contract

Default path:

```bash
eddy doctor
eddy edit <source-folder> --json
eddy status <run-dir> --json
eddy artifacts <run-dir> --json
eddy scorecard <run-dir> --json
eddy bakeoff <source-folder> --json
```

`eddy edit` is autonomous by default. When `OPENROUTER_API_KEY` is configured, the editor+critic loop can
author the initial intent inside the cloud budget. A host agent may also supply a reviewed intent through
`--intent` or the MCP `intent` / `intent_json` arguments. Eddy still clamps the intent to frozen identities,
source duration, and quality gates.

Use `eddy audio-proof <run-dir> --cloud-budget 25 --json` to retry Studio Sound or approved cloud audio
after credentials become available. It may remux the long video only after provider parity passes and media
integrity re-passes.

Use `eddy review <run-dir> --long-edit 8 --motion 8 --audio 8 --shorts 8` only when Lennox would publish it.
Review scores do not override machine blockers.

## Motion and identity

HyperFrames is the default renderer for long overlays, motion graphics, caption surfaces, and Shorts
packaging. The six identities are frozen systems, not restyleable themes:

- `threadify-fc`
- `code-cinema`
- `liquid-glass`
- `broadcast-receipts`
- `kinetic-poster`
- `editorial-data`

First 60 seconds should carry dense identity motion. Later sections should use sparse, content-aware
overlays and callouts. Shorts must be 1080x1920 with burned kinetic captions.

## Audio

Descript Studio Sound is first choice, using extracted audio only. Do not upload full source video by
default. Strong Studio Sound passes only when export duration/content parity is automatically proven.

If Descript is unavailable or fails parity, try Auphonic or ElevenLabs only when configured and cost-capped.
Local loudness is a degraded fallback and must keep the publishability blocker visible.

## Workflow

- Main branch is trunk. Commit small, tested slices straight to `main`, then push `origin main`.
- Run focused tests first, then the full relevant gate for behavior changes.
- Always run `python3 scripts/contract_audit.py`, `python3 scripts/public_scrub_check.py`, and
  `git diff --check` before public handoff.
- Keep proof layers separate: local tests, CI green, repo setup, hero-run media, cloud/cost proof,
  Studio Sound proof, human review, and final publishability are different claims.
- Do not weaken gates to pass a run. Fix the gate deliberately or report the exact blocker with receipts.

## Verified commands

```bash
.venv/bin/eddy --help
.venv/bin/pytest
.venv/bin/ruff check src tests scripts/contract_audit.py
.venv/bin/mypy src/eddy_v2
npm run renderer:doctor
.venv/bin/pytest -q --cov=eddy_v2 --cov-report=term-missing
python3 scripts/public_scrub_check.py
python3 scripts/contract_audit.py
git diff --check
```
