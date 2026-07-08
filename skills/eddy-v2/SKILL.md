---
name: eddy-v2
description: Run Eddy V2 proof-gated YouTube edits from raw footage folders. Use for raw creator footage to long video, Shorts, launch kit, scorecard, and receipts.
---

# Eddy V2 Skill

This is the shared Codex and Claude skill for Eddy V2. Use MCP tools first when
available. Fall back to the CLI.

## Default workflow

1. Run `eddy doctor`.
2. Run `eddy edit <folder>` for autonomous editing.
3. Read `<folder>/eddy-runs/<run>/scorecard.md`.
4. If status is blocked, report the exact blocker and receipts path.
5. If Studio Sound credentials become available after a run, use `eddy audio-proof <run>` to retry cloud audio proof from the existing extracted WAV instead of rerunning the full edit.
6. If Lennox gives 8/10 quality scores, record them with `eddy review <run>` instead of editing the scorecard by hand.

For MCP host-agent repair loops, call `eddy_v2_scorecard` with `json: true` or `format: "json"`
when you need the same structured payload as `eddy scorecard <run> --json`; omit those options for
the human-facing Markdown scorecard.

Motion proof lives under each run's `motion/` projects. Expect `frame.md`, `storyboard.md`,
`storyboard.html`, `motion-plan.json`, `motion-collision-proof.json`, `motion-lint.json`, and
`motion-inspect.json` before treating overlays or Shorts cards as compositor-safe.

## Host-agent intent path

If you have enough context to provide or repair the edit intent yourself, pass a JSON object with
`target_duration_s`, `identity`, `shorts_target`, `hook`, and `title`:

- MCP: call `eddy_v2_edit_start` with `intent` or `intent_json`.
- CLI fallback: write the object to a local file and run `eddy edit <folder> --intent <intent.json>`.

Eddy validates the host intent against frozen identities, source duration, and the default YouTube
floor, records `host_intent` receipts, and skips OpenRouter for that run.

## Review path

`eddy review <run> --long-edit <score> --motion <score> --audio <score> --shorts <score>` records the
human bakeoff verdict. The command keeps `publishable_8_of_10` false when any score is below 8 or
when machine/audio quality blockers such as `strong_studio_sound_not_proven` remain.

## Audio proof retry

`eddy audio-proof <run>` verifies the run's source hashes, reuses `audio/source-audio.wav`, retries the
configured cloud audio providers under the current cost cap, and remuxes `final/video.mp4` only when
cloud audio passes parity. Use `--local-only` when cloud egress is forbidden; it will refuse provider
branches and keep the existing audio blockers.

When credentials live in 1Password, do not print or paste token values. First make sure `op whoami`
is signed in, then run the retry through 1Password references:

```bash
op run --env-file .env.audio -- eddy audio-proof <run> --cloud-budget 25 --json
```

Prefer `DESCRIPT_API_KEY` for Strong Studio Sound. `AUPHONIC_API_KEY` plus `AUPHONIC_PRESET` /
`AUPHONIC_PRESET_UUID`, or `ELEVENLABS_API_KEY`, can prove an approved cloud fallback but not Descript
Studio Sound.

## Hard boundaries

- Never edit, move, delete, or overwrite raw source files.
- No platform publish, full-video upload, or scheduling actions exist in Eddy V2.
- The only permitted egress is receipted, cost-capped model/audio quality work when cloud mode is
  allowed and credentials are configured.
- `--local-only` must be used whenever the user forbids cloud/model/audio/image egress.
- Do not call a run publishable until Lennox scores long edit, motion, audio, and Shorts at 8/10+.
