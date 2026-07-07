# EDDY-PLAYBOOK.md - V2 taste doctrine and edit contract

Eddy V2 exists to make "edit this" real:

raw folder in -> proof-gated long YouTube edit + quality-gated Shorts + launch kit out, or exact blockers
with receipts.

The owner cares about quality first, then cost, then time. Fast bad output is a failure. Beautiful output
without proof is also a failure.

## One-command contract

The default UX is:

```bash
eddy edit <source-folder> --json
```

The command should autonomously produce the best package it can under the run policy. If a host agent has
better creative judgment than the model loop for a specific run, it can supply an intent:

```bash
eddy edit <source-folder> --intent intent.json --json
```

MCP mirrors the same flow through `eddy_v2_edit_start` with optional `intent` / `intent_json`, plus read tools
for status, artifacts, scorecard, bakeoff, review, and audio proof.

Never turn a red gate green by lowering the bar. Tighten or repair the system, rerun, and keep receipts.

## Editorial taste

The long video should feel like a finished YouTube edit, not a trimmed meeting recording:

- Cut dead air and weak repeats.
- Prefer the last clean retake when repeated attempts are ambiguous.
- Keep the argument legible: hook, escalation, proof, payoff.
- Use screen footage as evidence, not wallpaper.
- Add callouts only when they help the viewer understand what changed or why it matters.
- Keep launch copy grounded in the actual video and transcript. No fake claims.

If there is no transcript sidecar, Eddy may use fallback planning, but it must receipt that limitation.

## Motion taste

HyperFrames owns overlays, motion graphics, captions, and Shorts packaging. The first 60 seconds should be
dense with identity motion because that is where trust and attention are won. Later motion should become
sparser and more content-aware.

Frozen identity systems:

- `threadify-fc`: founder-operator, Full Circle / Threadify energy, sharp receipts, dark/fire register.
- `code-cinema`: cinematic developer proof, terminal/code language, high contrast.
- `liquid-glass`: polished product demo energy, restrained translucent surfaces.
- `broadcast-receipts`: newsroom/proof-desk pacing, lower thirds, ledgers, timestamps.
- `kinetic-poster`: bold campaign typography, poster-scale kinetic cards.
- `editorial-data`: charts, numbers, evidence overlays, calm analysis.

Do not restyle an identity per video. Compose with the system as shipped.

## Shorts taste

Shorts are not filler. They should create a reason to watch the long video:

- 1080x1920.
- Burned kinetic captions.
- Clear hook in the opening seconds.
- A self-contained arc that withholds the long-video payoff.
- Three passing Shorts minimum when the source supports it.

If fewer than three Shorts are actually good, keep the long video and green Shorts, then record
`shorts_quality_shortfall`. Never pad with weak clips.

## Audio taste

Studio Sound is a hard quality expectation, not a nice-to-have label.

Priority:

1. Descript API Studio Sound using extracted audio only.
2. Auphonic when configured.
3. ElevenLabs Audio Isolation when configured.
4. Local loudness fallback as a blocked, degraded partial.

Strong Studio Sound passes only when provider export parity is proven and the polished audio is actually
remuxed into the long video. Missing credentials, local-only refusal, failed parity, or degraded local audio
must stay visible in `audio-proof.json`, `scorecard.json`, `bakeoff.json`, and receipts.

## Proof doctrine

Every run must separate these proof layers:

- repo setup proof
- test proof
- source-safety proof
- hero-run media proof
- motion/caption proof
- Shorts yield proof
- cloud/cost proof
- audio quality proof
- human 8/10 review proof
- final publishability

Do not collapse "video exists" into "Eddy is done." A run can have long media, Shorts, launch kit, source
hashes, and CI green while still being blocked on Studio Sound or Lennox review.

## Bakeoff doctrine

The Bakeoff Hero Video is the Codex custom-models footage:

- `/Users/lennoxsaint/content-pipeline/2026-06-22-codex-custom-models/source/raw/camera.mp4`
- `/Users/lennoxsaint/content-pipeline/2026-06-22-codex-custom-models/source/raw/screen.mp4`

`eddy bakeoff <source-folder>` compares V2 against current Eddy output only when read-only current-output
proof exists. If no comparable current Eddy final exists, report `current_output_proof_missing`; do not invent
a winner.

Winner bar:

- Lennox would publish the long video.
- Long edit is 8/10+.
- Motion is 8/10+.
- Audio is 8/10+.
- Shorts are 8/10+.
- No machine blockers remain.

Until then, the honest output is a proof-gated partial with exact next actions.

## Stop conditions

Stop and report exact blockers when:

- source hashes change
- source media is ambiguous or unavailable
- raw source mutation would be required
- credentials are missing for the required quality path
- cloud spend would exceed the run cap
- `--local-only` would need egress to proceed
- long media is corrupt or missing
- motion/captions are corrupt
- fewer than three Shorts pass and the shortfall is not receipted
- Lennox review is required for publishability

The system wins by being honest. "Blocked with receipts" is better than a fake green package.
