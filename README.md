# Eddy V2

**Raw creator footage in. Proof-gated YouTube package out.**

Eddy V2 is a cloud-first, source-safe agentic video editor. It produces an edited long-form YouTube video, quality-gated Shorts, sidecar subtitles, launch metadata, a scorecard, and receipts. If it cannot prove the package is safe and creator-good, it returns exact blockers instead of pretending.

V2 is a separate repo from `lennoxsaint/eddy`. The old repo remains public and unchanged.

## Promise

`eddy edit <folder>` is autonomous by default:

- reads a footage folder
- never edits, moves, deletes, or overwrites raw sources
- hashes sources before and after the run
- writes outputs under `<folder>/eddy-runs/<run-slug>/`
- records model calls, cloud attempts, ffmpeg commands, HyperFrames commands, costs, fallbacks, gate verdicts, and blockers in `receipts.jsonl`
- writes failed renders/samples to `quarantine/`, never `final/`

The user-visible result is either a **Proof-Gated One-Command** package or an exact blocker packet.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
eddy doctor
```

## CLI

```bash
eddy doctor
eddy edit /path/to/footage
eddy status /path/to/footage/eddy-runs/<run>
eddy artifacts /path/to/footage/eddy-runs/<run>
eddy scorecard /path/to/footage/eddy-runs/<run>
eddy bakeoff /path/to/footage
```

`--local-only` refuses OpenRouter, Descript, Auphonic, ElevenLabs, cloud render, and image/model uploads. Cloud quality mode is otherwise allowed by default when credentials are configured and cost-capped.

## Audio Quality

When `DESCRIPT_API_KEY` is configured, Eddy tries Descript Studio Sound first using only the extracted audio WAV. It requests a direct upload URL, uploads audio bytes only, prompts Underlord for Studio Sound without timing/content edits, publishes an audio export, downloads it, and marks Strong Studio Sound only if duration parity passes. Tokens and signed URLs are never written to receipts.

For dry tests, set `EDDY_V2_FAKE_DESCRIPT=1` with a dummy `DESCRIPT_API_KEY`; this exercises the Studio Sound receipt/parity path without network egress or credits. `--local-only` refuses Descript even when a key or fake mode is present.

## Scope Boundaries

Eddy V2 has no publish, upload, scheduling, or hosted app code. It produces files and proof artifacts only.

## Bake-Off

See `docs/BAKEOFF.md` for the one-week comparison plan against current Eddy, V2 local-only, V2 cloud quality, and the `video-use` UX baseline.

## Motion Identities

The six approved identities are frozen systems, not restyleable themes:

- `threadify-fc`
- `code-cinema`
- `liquid-glass`
- `broadcast-receipts`
- `kinetic-poster`
- `editorial-data`

HyperFrames is the default motion renderer. V2 generates run-local HyperFrames projects and receipts lint, inspect, and render attempts.
