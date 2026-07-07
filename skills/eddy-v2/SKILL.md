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

## Hard boundaries

- Never edit, move, delete, or overwrite raw source files.
- No publish, upload, or scheduling actions exist in Eddy V2.
- `--local-only` must be used whenever the user forbids cloud/model/audio/image egress.
- Do not call a run publishable until Lennox scores long edit, motion, audio, and Shorts at 8/10+.
