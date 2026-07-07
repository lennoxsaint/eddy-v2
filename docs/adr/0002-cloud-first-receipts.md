# Cloud-First With Receipts

V2 defaults to a Cloud Quality Profile because the product goal prioritizes output quality over local purity. Every external model, audio, render, or upload boundary is cost-capped and recorded in receipts, and `--local-only` remains a hard egress refusal mode.

## Model boundary

OpenRouter is used as a built-in editor+critic loop, not a per-run model council. The editor proposes the compact edit intent; the critic either approves it or returns a bounded repair object. Every model call, repair, fallback, and cost estimate lands in `receipts.jsonl`. If the loop fails, Eddy falls back to the deterministic default intent and records the exact failure instead of blocking local rendering.
