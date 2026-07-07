from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .cloud_quality import cloud_audio_profile
from .receipts import Receipts

PROVIDER_EVENTS = {
    "descript": "audio_descript_parity",
    "auphonic": "audio_auphonic_parity",
    "elevenlabs": "audio_elevenlabs_parity",
}

STRONG_BACKEND = "descript_studio_sound"
CLOUD_FALLBACK_BACKENDS = {"auphonic", "elevenlabs_audio_isolation"}
LOCAL_FALLBACK_BACKEND = "local_loudnorm_fallback"


def audio_gate_blockers(audio_summary: dict[str, Any] | None) -> list[str]:
    if not audio_summary:
        return ["audio_proof_missing"]
    if audio_summary.get("quality_status") in {"strong_studio_sound", "cloud_audio_fallback"}:
        return []
    quality_blockers = audio_summary.get("quality_blockers")
    if isinstance(quality_blockers, list) and quality_blockers:
        return [str(blocker) for blocker in quality_blockers]
    return ["audio_quality_gate_failed"]


def _latest(rows: list[dict[str, Any]], event: str) -> dict[str, Any] | None:
    for row in reversed(rows):
        if row.get("event") == event:
            return row
    return None


def summarize_audio_proof(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected = _latest(rows, "audio_polish") or {}
    selected_backend = selected.get("selected_backend")
    providers: dict[str, dict[str, Any]] = {}
    for provider, event in PROVIDER_EVENTS.items():
        row = _latest(rows, event) or {}
        providers[provider] = {
            "status": row.get("status") or "missing",
            "reason": row.get("reason"),
            "error": row.get("error"),
            "uploaded_media": row.get("uploaded_media"),
        }

    strong_studio_sound = selected_backend == STRONG_BACKEND and providers["descript"]["status"] == "pass"
    cloud_polish_proven = selected_backend in CLOUD_FALLBACK_BACKENDS
    if strong_studio_sound:
        quality_status = "strong_studio_sound"
    elif cloud_polish_proven:
        quality_status = "cloud_audio_fallback"
    elif selected_backend == LOCAL_FALLBACK_BACKEND:
        quality_status = "local_degraded_fallback"
    else:
        quality_status = "audio_polish_missing"

    quality_blockers: list[str] = []
    if not strong_studio_sound:
        quality_blockers.append("strong_studio_sound_not_proven")
    if selected_backend == LOCAL_FALLBACK_BACKEND:
        quality_blockers.append("cloud_audio_credentials_missing_or_failed")
    if not selected_backend:
        quality_blockers.append("audio_polish_receipt_missing")

    return {
        "selected_backend": selected_backend,
        "output": selected.get("output"),
        "quality_status": quality_status,
        "strong_studio_sound": strong_studio_sound,
        "cloud_polish_proven": cloud_polish_proven,
        "quality_blockers": quality_blockers,
        "cloud_quality_profile": {"audio": cloud_audio_profile()},
        "providers": providers,
    }


def read_json_object(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    parsed = json.loads(path.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, dict) else None


def write_audio_proof(run_dir: Path, receipts: Receipts) -> Path:
    proof = summarize_audio_proof(receipts.read_all())
    path = run_dir / "final" / "audio-proof.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    receipts.log(
        "audio_proof",
        status="pass",
        proof=str(path),
        selected_backend=proof["selected_backend"],
        quality_status=proof["quality_status"],
        strong_studio_sound=proof["strong_studio_sound"],
        quality_blockers=proof["quality_blockers"],
    )
    return path
