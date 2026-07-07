---
name: eddy-v2
description: Run Eddy V2 proof-gated YouTube edits from raw footage folders. Use for raw creator footage to long video, Shorts, launch kit, scorecard, and receipts.
---

# Eddy V2 Skill

Use MCP tools first when available. Fall back to the CLI.

## Default workflow

1. Run `eddy doctor`.
2. Run `eddy edit <folder>` for autonomous editing.
3. Read `<folder>/eddy-runs/<run>/scorecard.md`.
4. If status is blocked, report the exact blocker and receipts path.
5. If Lennox gives 8/10 quality scores, record them with `eddy review <run>` instead of editing the scorecard by hand.

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

## Hard boundaries

- Never edit, move, delete, or overwrite raw source files.
- No publish, upload, or scheduling actions exist in Eddy V2.
- `--local-only` must be used whenever the user forbids cloud/model/audio/image egress.
- Do not call a run publishable until Lennox scores long edit, motion, audio, and Shorts at 8/10+.
