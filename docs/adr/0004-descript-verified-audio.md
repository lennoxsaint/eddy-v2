# Descript-Verified Audio Adapter

V2 tries Descript Studio Sound first using extracted audio only, but it may satisfy Strong Studio Sound only after automated export parity proves the polished audio actually comes back. If parity fails or credentials are absent, V2 falls back to configured Auphonic or ElevenLabs paths, then local polish as a recorded lower-quality fallback.

## Implementation contract

- Eddy extracts `source-audio.wav` locally and never uploads full source video for Studio Sound by default.
- With `DESCRIPT_API_KEY` configured and `--local-only` off, Eddy estimates and cost-caps the Descript audio attempt before network egress.
- The live adapter follows Descript's direct-upload flow: request signed upload URLs with `POST /jobs/import/project_media`, upload only the extracted WAV bytes, poll `GET /jobs/{job_id}`, run `POST /jobs/agent` with a one-shot Studio Sound-only prompt, publish audio with `POST /jobs/publish`, then download the exported audio.
- Receipts record API paths, job ids, redacted job summaries, upload byte counts, cloud/cost decisions, and parity verdicts. Bearer tokens and signed upload/download URLs are never written to receipts.
- Strong Studio Sound passes only when the downloaded export exists, has nonzero duration, and matches the extracted source duration within tolerance. Otherwise Eddy continues to the next configured backend or local loudness fallback.
- `EDDY_V2_FAKE_DESCRIPT=1` is for tests and dry proof only. It exercises the same receipt/parity contract without contacting Descript or spending credits.
