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
eddy bakeoff /path/to/footage --current-run /Users/lennoxsaint/eddy/runs/<run>
```

`--local-only` refuses OpenRouter, Descript, Auphonic, ElevenLabs, cloud render, and image/model uploads. Cloud quality mode is otherwise allowed by default when credentials are configured and cost-capped.

## Model Autonomy

When `OPENROUTER_API_KEY` is configured, Eddy runs a bounded editor+critic loop before rendering: the editor proposes `intent.json`, the critic approves or returns a repair object, and the final intent is clamped back to frozen identities and source duration. The loop is fully receipted and cost-capped. Eddy does not run a model council on every edit; escalation belongs in the bakeoff workflow after repeated failures.

## Transcript Sidecars

If the footage folder contains `transcript.vtt`, `transcript.srt`, `transcript.txt`, `captions.vtt`, or `captions.srt`, Eddy parses it into `transcript-cues.json`, derives semantic launch-kit chapters, and prefers transcript-backed Shorts anchors. Source media still stays read-only. If no transcript sidecar exists, Eddy records `transcript_source_missing`, uses audio-density planning, and marks launch-kit chapters as fallback.

## Audio Quality

When `DESCRIPT_API_KEY` is configured, Eddy tries Descript Studio Sound first using only the extracted audio WAV. It requests a direct upload URL, uploads audio bytes only, prompts Underlord for Studio Sound without timing/content edits, publishes an audio export, downloads it, and marks Strong Studio Sound only if duration parity passes. Tokens and signed URLs are never written to receipts.

If Descript is missing or fails parity, Eddy tries Auphonic when `AUPHONIC_API_KEY` and `AUPHONIC_PRESET` or `AUPHONIC_PRESET_UUID` are configured, then ElevenLabs Audio Isolation when `ELEVENLABS_API_KEY` is configured. Both fallbacks upload only the extracted WAV, charge against the same run budget, and must pass duration parity before selection. If every cloud backend is missing, refused, or fails, Eddy uses the local loudness fallback and records the lower-quality selection.

For dry tests, set `EDDY_V2_FAKE_DESCRIPT=1`, `EDDY_V2_FAKE_AUPHONIC=1`, or `EDDY_V2_FAKE_ELEVENLABS=1` with dummy provider credentials; this exercises the same receipt/parity path without network egress or credits. `--local-only` refuses all cloud audio providers even when fake mode is present.

## Proof Gates

Before a run can finish as complete, Eddy gates source hashes, HyperFrames motion artifacts, timed caption artifacts, caption sidecars, long-video media integrity, Shorts geometry/duration, launch-kit presence, cost cap, and final ffprobe output. Corrupt Shorts are moved to `quarantine/` and do not count toward the Shorts yield; corrupt long video, motion, captions, source safety, or launch package blocks the run.

## Scope Boundaries

Eddy V2 has no publish, upload, scheduling, or hosted app code. It produces files and proof artifacts only.

## Bake-Off

See `docs/BAKEOFF.md` for the one-week comparison plan against current Eddy, V2 local-only, V2 cloud quality, and the `video-use` UX baseline. `eddy bakeoff` now writes `bakeoff.json` and `bakeoff.md` into the V2 run folder. It compares against an explicit `--current-run` when provided, otherwise it searches read-only current-Eddy runs under `/Users/lennoxsaint/eddy/runs`; if no final current-Eddy media proof is found, the report records `current_output_proof_missing` instead of inventing a comparison.

## Motion Identities

The six approved identities are frozen systems, not restyleable themes:

- `threadify-fc`
- `code-cinema`
- `liquid-glass`
- `broadcast-receipts`
- `kinetic-poster`
- `editorial-data`

HyperFrames is the default motion renderer. V2 generates run-local HyperFrames projects and receipts lint, inspect, and render attempts.
Long-form overlays keep the first 60 seconds dense, then switch to sparse transcript- or cut-plan-aware beat cards for later sections. The motion plan records `dense_first_60_s`, `sparse_overlay_count`, and each sparse overlay in `motion-plan.json`.
