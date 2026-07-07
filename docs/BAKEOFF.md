# Eddy V2 One-Week Bake-Off

The bake-off exists to answer one question: can Eddy V2 beat the current Eddy path on the hero footage without bloating the repo again?

## Hero Fixture

- Camera: `/Users/lennoxsaint/content-pipeline/2026-06-22-codex-custom-models/source/raw/camera.mp4`
- Screen: `/Users/lennoxsaint/content-pipeline/2026-06-22-codex-custom-models/source/raw/screen.mp4`
- Target: one proof-gated long YouTube edit, at least three quality-gated Shorts when the source can honestly support them, sidecars, launch kit, scorecard, receipts.

## Competitors

1. Current Eddy repo.
2. Eddy V2 local-only.
3. Eddy V2 Cloud Quality Profile.
4. `video-use`-style operator baseline: agent drives a direct raw-footage workflow and reports where the UX is smoother than V2.

## Daily Loop

1. Run the same hero fixture once per candidate path.
2. Preserve the full run folder.
3. Run `eddy bakeoff <hero-folder> --current-run <current-eddy-run>` when a known current Eddy run exists. If the current run is not supplied, Eddy searches `/Users/lennoxsaint/eddy/runs` read-only and writes `current_output_proof_missing` when it cannot prove a comparable final video.
4. Watch the first five minutes, one middle segment, and all Shorts.
5. Score quality first, then time, then cost.
6. Record all blockers in receipts and a human scorecard. Do not patch around a blocker without adding a regression test or a gate.

## Scorecard

Quality is 70 points:
- Long edit story coherence: 20
- Cut pacing and dead-air removal: 15
- Audio polish: 10
- Motion graphics and overlays: 10
- Captions and sidecars: 5
- Shorts yield and watchability: 10

Reliability is 20 points:
- Source immutability: 5
- Reproducible run folder: 5
- Receipts/gates explain every decision: 5
- Quarantine is honest: 5

Cost and time are 10 points:
- Cloud spend stays inside the declared run cap: 5
- Wall-clock time is acceptable for the quality tier: 5

## OpenRouter Council Roster

Use this as a redacted council setup; do not send private raw footage, transcripts, source code, or identity files to external models without explicit approval.

- Default editor/critic: `anthropic/claude-sonnet-5`.
- Hard chair review: `anthropic/claude-opus-4.8` or `openai/gpt-5.5`.
- Cheap extraction/triage: `deepseek/deepseek-v4-flash` or another current high-throughput model only for non-private summaries.
- Video-aware auxiliary: a current multimodal long-context model only after inputs are redacted or converted to non-sensitive sampled observations.

Live OpenRouter data checked on 2026-07-07 favored Claude/Opus/Sonnet and GPT-5.5 for high-end agentic/coding work, while traffic patterns showed cheaper high-throughput models dominate workflow execution and classification. That is a routing hint, not an automatic quality claim.

## Stop Conditions

- Any source hash changes.
- Any unreceipted cloud call, upload, model call, or cost.
- A final artifact contains a known failed or partial render.
- Fewer than three Shorts are produced without a `shorts_quality_shortfall` receipt.
- A run claims "publishable" without Lennox review.
- A bakeoff claims a current-Eddy comparison without a discovered or explicit current run containing final media proof.

## Win Condition

Eddy V2 wins only if the Cloud Quality Profile produces the best watched output and its receipts make the run easier to trust than current Eddy. If local-only wins quality, cloud additions get demoted. If `video-use` wins UX but V2 wins proof, port the UX flow without weakening gates.
