# Research Notes

## 2026-07-07 Repo Scan

The best base is a hybrid, not a direct fork.

- `browser-use/video-use`: strongest UX baseline. Its promise is raw footage in a folder and `final.mp4` out through a coding agent. Eddy V2 should copy the UX shape, not the exact implementation.
- `heygen-com/hyperframes`: strongest motion-rendering foundation for agent-owned overlays, captions, title cards, and Shorts packaging. Eddy V2 should make this the default motion surface.
- `samuraigpt/ai-youtube-shorts-generator`: useful reference for highlight detection and vertical Shorts packaging, but it is a Shorts-first system rather than a long-edit proof-gated editor.
- `video-db/Director` and `HKUDS/VideoAgent`: useful architectural references for video-agent orchestration, search, and multi-tool routing. They are too framework-heavy to be Eddy V2's core.
- `noeltock/video-editor`: useful screen-plus-camera editing reference. It validates the idea that a Claude/Codex skill can manufacture polished screen-recording edits, but Eddy V2 still needs its own source immutability receipts and public proof gates.
- `GVCLab/CutClaw`: useful research direction for hour-long footage and music-synchronized short extraction, but not the immediate implementation base.

## 2026-07-07 Audio API Notes

Descript is still the preferred Studio Sound target, but V2 must treat it as an adapter with proof requirements:

- Public Descript docs describe API-driven project import/edit workflows and Studio Sound/Underlord automation.
- Descript states API/MCP usage can consume media minutes and AI credits.
- Studio Sound failures and long-processing cases are documented, especially for noisy or very large files.
- Therefore V2 must prove upload, enhancement, and exported-audio parity before it claims Strong Studio Sound. Until then, the local loudness/cleanup chain is a lower-quality fallback with receipts.

## Recommendation

Start from this V2 repo. Keep `video-use` as the UX comparator, HyperFrames as the motion renderer, and current Eddy gates as non-negotiable rules. Do not fork a large video-agent framework unless the one-week bake-off proves V2 cannot reach coherent long-edit quality with a simpler orchestrator.
