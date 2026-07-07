# Eddy V2

[![CI](https://github.com/lennoxsaint/eddy-v2/actions/workflows/ci.yml/badge.svg)](https://github.com/lennoxsaint/eddy-v2/actions/workflows/ci.yml)

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

`eddy doctor` fails if any required runtime tool is missing: `ffmpeg`, `ffprobe`, `node`, or `npx`.
It also reports a secret-safe Cloud Quality Profile for models and audio, including whether OpenRouter
autonomy is configured, which audio provider credentials are present, and the exact environment
variable options needed to unblock cloud model or audio proof.

## CLI

```bash
eddy doctor
eddy edit /path/to/footage
eddy edit /path/to/footage --intent /path/to/intent.json
eddy status /path/to/footage/eddy-runs/<run>
eddy artifacts /path/to/footage/eddy-runs/<run>
eddy scorecard /path/to/footage/eddy-runs/<run>
eddy review /path/to/footage/eddy-runs/<run> --long-edit 8 --motion 8 --audio 8 --shorts 8
eddy bakeoff /path/to/footage
eddy bakeoff /path/to/footage --current-run /Users/lennoxsaint/eddy/runs/<run>
```

Read commands accept `--json` for explicit machine-readable output; `eddy scorecard <run> --json` returns `scorecard.json` instead of the default Markdown scorecard.

`--local-only` refuses OpenRouter, Descript, Auphonic, ElevenLabs, cloud render, and image/model uploads. Cloud quality mode is otherwise allowed by default when credentials are configured and cost-capped.

Run `python scripts/contract_audit.py` before public handoff. It checks the repo-scope contract: MIT license, no runtime dependencies, permissive build/dev dependencies, required CLI and MCP surfaces, the six frozen identities, required docs/ADRs/skill files, and absence of social/video publishing integrations.

## Model Autonomy

When `OPENROUTER_API_KEY` is configured, Eddy runs a bounded editor+critic loop before rendering: the editor proposes `intent.json`, the critic approves or returns a repair object, and the final intent is clamped back to frozen identities and source duration. The loop is fully receipted and cost-capped. Eddy does not run a model council on every edit; escalation belongs in the bakeoff workflow after repeated failures.

For the default autonomous YouTube edit, model output may improve hook/title/identity selection but may not shrink the long-form duration below Eddy's default floor or reduce the target below three Shorts. Smaller test/sample edits are allowed only when the operator explicitly passes `--target-duration`.

Host agents can bypass OpenRouter by supplying a reviewed intent through `--intent` or the MCP `intent` / `intent_json` arguments. Eddy still validates frozen identity, duration, and Shorts fields, writes the final `intent.json`, records `host_intent` receipts, and skips the OpenRouter editor+critic loop for that run.

## Transcript Sidecars

If the footage folder, its project parent, or a known `edit/descript-export/` sibling contains `transcript.vtt`, `transcript.srt`, `transcript.md`, `transcript.txt`, `captions.vtt`, `captions.srt`, or `captions.md`, Eddy parses it into `transcript-cues.json`, derives semantic launch-kit chapters, and prefers transcript-backed Shorts anchors. Markdown transcripts may be plain paragraphs or Descript-style `[00:01:00]` marked exports. Source media still stays read-only. If no transcript sidecar exists, Eddy records `transcript_source_missing`, uses audio-density planning, and marks launch-kit chapters as fallback.

## Edit Decision Sidecars

If the footage folder, its project parent, or a known `edit/` sibling contains `edit-decisions.json`, Eddy treats its ordered `segments` as a deterministic story assembly. Each segment needs `start` and `end` source seconds, with an optional `id`. Eddy truncates the segment list to the target long-video duration, renders those source intervals gaplessly, extracts only those audio intervals for polish, maps launch-kit chapters onto the edited timeline, and receipts the decision with `edit_decision_sidecar`, `long_segment_render`, and `long_segment_concat` rows. If no valid sidecar exists, Eddy falls back to silence-detected planning.

Long-form `captions.json`, `subtitles.srt`, and `subtitles.vtt` are timed editorial callouts unless `final/caption-provenance.json` proves otherwise. V2 writes that provenance file on every new render and marks `speech_accurate_subtitles_not_proven` when the sidecars are useful motion/caption overlays rather than verbatim speech subtitles. This is a quality warning for review and bakeoff scoring, not a source-safety failure.

## Audio Quality

When `DESCRIPT_API_KEY` is configured, Eddy tries Descript Studio Sound first using only the extracted audio WAV. It requests a direct upload URL, uploads audio bytes only, prompts Underlord for Studio Sound without timing/content edits, publishes an audio export, downloads it, and marks Strong Studio Sound only if duration parity passes. Tokens and signed URLs are never written to receipts.

If Descript is missing or fails parity, Eddy tries Auphonic when `AUPHONIC_API_KEY` and `AUPHONIC_PRESET` or `AUPHONIC_PRESET_UUID` are configured, then ElevenLabs Audio Isolation when `ELEVENLABS_API_KEY` is configured. Both fallbacks upload only the extracted WAV, charge against the same run budget, and must pass duration parity before selection. If every cloud backend is missing, refused, or fails, Eddy uses the local loudness fallback and records the lower-quality selection.

Every run that reaches audio writes `final/audio-proof.json`. It records the selected backend, each provider parity result, whether Strong Studio Sound was proven, and any publishability quality blockers such as `strong_studio_sound_not_proven`. Descript parity or a proven cloud fallback can pass the machine audio gate. A local fallback is a reviewable partial only: Eddy still writes the long video, Shorts, launch kit, and review packet, but the run status is blocked until cloud audio proof is upgraded.

`final/audio-proof.json` also includes the same secret-safe Cloud Quality Profile from `eddy doctor`
so a blocked run explains the exact credential options without exposing token values.

Use `eddy audio-proof <run>` when a run already exists but Studio Sound credentials become available later. It reuses `audio/source-audio.wav`, verifies source hashes from `manifest.json`, retries Descript/Auphonic/ElevenLabs under the same cost cap, remuxes `final/video.mp4` when cloud audio passes, backs up the previous long video in `quarantine/`, and refreshes `final/audio-proof.json`, the scorecard, launch kit, and review packet. `eddy audio-proof --local-only <run>` refuses cloud audio before upload/fake-provider branches and leaves the existing proof blockers in place.

For dry tests, set `EDDY_V2_FAKE_DESCRIPT=1`, `EDDY_V2_FAKE_AUPHONIC=1`, or `EDDY_V2_FAKE_ELEVENLABS=1` with dummy provider credentials; this exercises the same receipt/parity path without network egress or credits. `--local-only` refuses all cloud audio providers even when fake mode is present.

## Proof Gates

Before a run can finish as complete, Eddy gates source hashes, cut integrity, HyperFrames motion artifacts, timed caption artifacts, caption sidecars, long-video media integrity, Shorts geometry/duration, audio-proof generation, `audio_quality`, launch-kit presence, review-packet generation, cost cap, and final ffprobe output. Corrupt Shorts are moved to `quarantine/` and do not count toward the Shorts yield; corrupt long video, motion, captions, source safety, cut integrity, launch package, missing/degraded audio proof, or review packet blocks the run.

Completed runs also write `final/review/review-packet.json` and `final/review/README.md` with sampled long-video and Shorts frames plus playable `final/review/reels/long-review-reel.mp4` and `final/review/reels/shorts-review-reel.mp4`. That packet keeps the human taste gate explicit and fast to judge: Lennox must score the long edit, motion graphics, audio polish, and Shorts watchability at 8/10+ before Eddy can claim a publishable bakeoff win.

Use `eddy review <run> --long-edit <score> --motion <score> --audio <score> --shorts <score>` to record that taste review back into the run. The command updates the review packet and scorecard, but it keeps `publishable_8_of_10` false when machine blockers or audio quality blockers are still present.

`scorecard.json` includes `proof_layers` so operators can inspect the run without collapsing proof states:
`hero_run_proof`, `shorts_proof`, `cloud_cost_proof`, `human_review_proof`, `caption_proof`, and `final_publishability`.
The same section is refreshed after `eddy edit`, `eddy audio-proof`, and `eddy review`. When blocked,
it includes secret-safe unblock actions: provider environment-variable options, the exact
`eddy audio-proof` retry command, and the `eddy review` command template. It never records token values.

## Scope Boundaries

Eddy V2 has no publish, upload, scheduling, or hosted app code. It produces files and proof artifacts only.

## Bake-Off

See `docs/BAKEOFF.md` for the one-week comparison plan against current Eddy, V2 local-only, V2 cloud quality, and the `video-use` UX baseline. `eddy bakeoff` now writes `bakeoff.json` and `bakeoff.md` into the V2 run folder. It compares against an explicit `--current-run` when provided, otherwise it searches read-only current-Eddy runs under `/Users/lennoxsaint/eddy/runs`; if no final current-Eddy media proof is found, the report records `current_output_proof_missing` instead of inventing a comparison. The bakeoff report also includes `completion_audit`, which separates repo setup proof, test proof, hero-run proof, cloud/cost proof, human review proof, and remaining blockers.

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
Every motion project also writes `storyboard.md`, `storyboard.html`, and `motion-collision-proof.json`; the motion artifact gate refuses missing storyboard or failed collision proof before compositing is considered safe.
