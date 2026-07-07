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

**Transcript Sidecar**:
A creator-provided `.vtt`, `.srt`, or `.txt` file placed beside the raw footage so Eddy can make semantic chapter and Shorts-anchor decisions without mutating source media.
_Avoid_: Hidden transcription job, source edit, unreceipted metadata

**Semantic Chapter**:
A launch-kit chapter derived from transcript language and backed by a `transcript` receipt, with a fallback marker when no transcript sidecar exists.
_Avoid_: Generic chapter, fake understanding, unproven editorial beat

## Relationships

- A **Proof-Gated One-Command** run may use the **Cloud Quality Profile** unless `--local-only` is set.
- An **Identity Pack** drives all default HyperFrames motion surfaces.
- A **Quarantined Partial** may be cited in receipts, but it must not appear in `final/`.
- The **Bakeoff Hero Video** is the acceptance target after the full V2 feature floor exists.
- A **Transcript Sidecar** can produce **Semantic Chapter** entries, but the run remains complete without one only when the fallback is receipted.
- An **8/10 Quality Review** can only mark a run publishable when every score is 8+ and no machine or audio quality blockers remain.
- An **Audio Proof Retry** may remove the Studio Sound blocker for an existing run, but only after the remuxed long video re-passes media integrity.

## Example Dialogue

> **Dev:** "The long video rendered, but only one Short passed. Is the run complete?"
> **Domain expert:** "Yes only if the long video gates pass and the run records a Shorts shortfall receipt instead of forcing filler."

> **Dev:** "Can I tweak `code-cinema` colors for this video?"
> **Domain expert:** "No. The **Identity Pack** is frozen. Compose with it; do not restyle it."

## Flagged Ambiguities

- "Perfectly edited" means **Proof-Gated One-Command**, not a universal subjective guarantee.
- "Cloud first" means the **Cloud Quality Profile**, not uncapped or silent uploads.
