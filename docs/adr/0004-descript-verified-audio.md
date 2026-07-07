# Descript-Verified Audio Adapter

V2 tries Descript Studio Sound first using extracted audio only, but it may satisfy Strong Studio Sound only after automated export parity proves the polished audio actually comes back. If parity fails or credentials are absent, V2 falls back to configured Auphonic or ElevenLabs paths, then local polish as a recorded lower-quality blocked partial.

## Implementation contract

- Eddy extracts `source-audio.wav` locally and never uploads full source video for Studio Sound by default.
- With `DESCRIPT_API_KEY` configured and `--local-only` off, Eddy estimates and cost-caps the Descript audio attempt before network egress.
- The live adapter follows Descript's direct-upload flow: request signed upload URLs with `POST /jobs/import/project_media`, upload only the extracted WAV bytes, poll `GET /jobs/{job_id}`, run `POST /jobs/agent` with a one-shot Studio Sound-only prompt, publish audio with `POST /jobs/publish`, then download the exported audio.
- Receipts record API paths, job ids, redacted job summaries, upload byte counts, cloud/cost decisions, and parity verdicts. Bearer tokens and signed upload/download URLs are never written to receipts.
- Strong Studio Sound passes only when the downloaded export exists, has nonzero duration, and matches the extracted source duration within tolerance. Otherwise Eddy continues to the next configured backend. If every cloud backend is missing, refused, or fails, Eddy may write a local loudness fallback for review, but `audio_quality` fails and the run status remains blocked.
- Existing runs can be upgraded with `eddy audio-proof <run>`. The command verifies the run manifest's source hashes, reuses `audio/source-audio.wav`, retries configured cloud audio providers, remuxes `final/video.mp4` only after provider parity passes, backs up the previous long video in `quarantine/`, and refreshes audio proof metadata across scorecard, launch kit, and review packet.
- `EDDY_V2_FAKE_DESCRIPT=1` is for tests and dry proof only. It exercises the same receipt/parity contract without contacting Descript or spending credits.
- Auphonic fallback uses the Simple API with an existing `AUPHONIC_PRESET` or `AUPHONIC_PRESET_UUID`, starts a production from the extracted WAV only, disables timing cutters, polls the production, downloads the first result file, and selects it only after `audio_auphonic_parity` passes.
- ElevenLabs fallback uses Audio Isolation with the extracted WAV only, converts the returned audio locally for remuxing, and selects it only after `audio_elevenlabs_parity` passes.
- `--local-only` refuses Descript, Auphonic, and ElevenLabs before any fake or live upload branch can run.
