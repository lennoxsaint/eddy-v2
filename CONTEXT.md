# Eddy V2 Context

Eddy V2 is an autonomous, proof-gated video editing context: raw creator footage enters, a long-form YouTube package and quality-gated Shorts exit, and every unsafe or unproven step is receipted as a blocker.

## Language

**Proof-Gated One-Command**:
An autonomous edit run that either produces a creator-good package with passing gates or returns exact blockers with receipts.
_Avoid_: Literal perfection, best effort, first draft

**Identity Pack**:
The frozen set of six approved motion design systems used for overlays, captions, motion graphics, and Shorts packaging.
_Avoid_: Theme, skin, style preset

**Cloud Quality Profile**:
The default V2 mode where approved external APIs may be used when configured, cost-capped, and fully receipted.
_Avoid_: Silent upload, local-only, uncapped cloud

**Quarantined Partial**:
A failed render, audio sample, motion output, or draft artifact kept for debugging but forbidden from final deliverables.
_Avoid_: Draft final, partial export, usable preview

**Bakeoff Hero Video**:
The single real layered Codex custom-models footage set used to judge whether V2 beats the current Eddy path.
_Avoid_: Cherry-picked demo, synthetic test, smoke clip

**8/10 Quality Review**:
The human taste verdict recorded by `eddy review`, with separate scores for long edit story, motion graphics, audio polish, and Shorts watchability.
_Avoid_: Implicit approval, green render, unrecorded opinion

**Audio Proof Retry**:
The `eddy audio-proof <run>` path that reuses an existing run's extracted WAV, rechecks source hashes, retries configured cloud audio providers, and remuxes the final long video only after parity passes.
_Avoid_: Full re-edit, source upload, proof-only audio that is not in the final video

**Proof Layers**:
The machine-readable split in `scorecard.json` and `bakeoff.json` that keeps hero-run media proof, Shorts yield proof, cloud/cost proof, human review, and final publishability separate.
_Avoid_: One green badge, vague completion, hidden blocker

**Unblock Actions**:
Secret-safe next actions inside the Proof Layers that name missing environment variables and exact retry/review commands without storing credential values.
_Avoid_: Secret capture, silent retry, hand-wavy next step

**Transcript Sidecar**:
A creator-provided `.vtt`, `.srt`, `.md`, or `.txt` file placed beside the raw footage, one level above a `raw/` folder, or inside a known Descript export sibling so Eddy can make semantic chapter and Shorts-anchor decisions without mutating source media.
_Avoid_: Hidden transcription job, source edit, unreceipted metadata

**Semantic Chapter**:
A launch-kit chapter derived from transcript language and backed by a `transcript` receipt, with a fallback marker when no transcript sidecar exists.
_Avoid_: Generic chapter, fake understanding, unproven editorial beat

**Caption Provenance**:
The proof file that says whether timed caption sidecars are speech-accurate subtitles or editorial callouts used for motion overlays.
_Avoid_: Assuming `.srt` means verbatim, hidden transcription claim, unlabelled captions

## Relationships

- A **Proof-Gated One-Command** run may use the **Cloud Quality Profile** unless `--local-only` is set.
- The **Cloud Quality Profile** covers OpenRouter model autonomy and external audio providers separately, so a run can have model intent ready while Studio Sound remains blocked.
- An **Identity Pack** drives all default HyperFrames motion surfaces.
- A **Quarantined Partial** may be cited in receipts, but it must not appear in `final/`.
- The **Bakeoff Hero Video** is the acceptance target after the full V2 feature floor exists.
- A **Transcript Sidecar** can produce **Semantic Chapter** entries, but the run remains complete without one only when the fallback is receipted.
- **Caption Provenance** may warn that sidecars are editorial callouts even when a **Transcript Sidecar** exists, because transcript-backed planning is separate from speech-accurate subtitle generation.
- An **8/10 Quality Review** can only mark a run publishable when every score is 8+ and no machine or audio quality blockers remain.
- An **Audio Proof Retry** may remove the Studio Sound blocker for an existing run, but only after the remuxed long video re-passes media integrity.
- **Proof Layers** are refreshed after edits, audio retries, and human reviews so a run can show green media proof while final publishability stays blocked.
- **Unblock Actions** explain exactly how to clear remaining blockers, but they do not execute cloud calls or reviews by themselves.

## Example Dialogue

> **Dev:** "The long video rendered, but only one Short passed. Is the run complete?"
> **Domain expert:** "Yes only if the long video gates pass and the run records a Shorts shortfall receipt instead of forcing filler."

> **Dev:** "Can I tweak `code-cinema` colors for this video?"
> **Domain expert:** "No. The **Identity Pack** is frozen. Compose with it; do not restyle it."

## Flagged Ambiguities

- "Perfectly edited" means **Proof-Gated One-Command**, not a universal subjective guarantee.
- "Cloud first" means the **Cloud Quality Profile**, not uncapped or silent uploads.
- "Subtitles" means timed sidecars; use **Caption Provenance** before treating them as speech-accurate.
