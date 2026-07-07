from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from .audio import polish_extracted_audio
from .commands import duration_s, ffprobe_json, run_command
from .cost import CostTracker
from .policy import RunPolicy
from .proof import read_json_object, write_audio_proof
from .qa import validate_long_video
from .receipts import Receipts
from .sources import sha256_file


def _latest_cost_spent(rows: list[dict[str, Any]]) -> float:
    spent = 0.0
    for row in rows:
        if row.get("event") == "cost_charge":
            try:
                spent = float(row.get("next_spent_usd", spent))
            except (TypeError, ValueError):
                continue
    return spent


def _rewrite_line(path: Path, prefix: str, replacement: str) -> None:
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    updated = [replacement if line.startswith(prefix) else line for line in lines]
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def _refresh_json_audio(path: Path, audio_proof_path: Path, proof: dict[str, Any], cost_summary: dict[str, float]) -> None:
    payload = read_json_object(path)
    if not payload:
        return
    payload["audio_proof_path"] = str(audio_proof_path)
    payload["audio_proof"] = proof
    if path.name == "scorecard.json":
        payload["cost"] = cost_summary
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _verify_source_manifest(run_dir: Path, receipts: Receipts) -> None:
    manifest = read_json_object(run_dir / "manifest.json")
    if not manifest:
        receipts.log("blocker", code="source_manifest_missing", run_dir=str(run_dir))
        raise RuntimeError("source_manifest_missing")

    sources = manifest.get("sources")
    before = manifest.get("source_sha256_before")
    if not isinstance(sources, dict) or not isinstance(before, dict):
        receipts.log("blocker", code="source_manifest_invalid", run_dir=str(run_dir))
        raise RuntimeError("source_manifest_invalid")

    for label, expected in before.items():
        path_text = sources.get(label)
        if not path_text:
            receipts.log("blocker", code="source_manifest_path_missing", label=label)
            raise RuntimeError(f"source_manifest_path_missing:{label}")
        path = Path(str(path_text))
        if not path.exists():
            receipts.log("blocker", code="source_missing_for_audio_retry", label=label, path=str(path))
            raise RuntimeError(f"source_missing_for_audio_retry:{label}")
        actual = sha256_file(path)
        receipts.log("source_hash", phase="audio_proof_retry", label=label, path=str(path), sha256=actual)
        if actual != expected:
            receipts.log("blocker", code="source_hash_changed", label=label, before=expected, after=actual)
            raise RuntimeError(f"source_hash_changed:{label}")


def _remux_final_video(run_dir: Path, audio: Path, receipts: Receipts) -> Path:
    final_video = run_dir / "final" / "video.mp4"
    if not final_video.exists():
        receipts.log("blocker", code="audio_retry_missing_final_video", run_dir=str(run_dir))
        raise RuntimeError("audio_retry_missing_final_video")

    expected_duration = duration_s(final_video)
    quarantine = run_dir / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    backup = quarantine / f"video-before-audio-proof-retry-{int(time.time())}.mp4"
    shutil.copy2(final_video, backup)
    receipts.log("quarantine_artifact", reason="audio_proof_retry_backup", path=str(backup))

    tmp = run_dir / "final" / "video.audio-proof-remux.tmp.mp4"
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(final_video),
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(tmp),
        ],
        receipts,
        event="ffmpeg",
        timeout_s=1800,
    )
    validate_long_video(run_dir, tmp, receipts, expected_duration_s=expected_duration)
    tmp.replace(final_video)
    (run_dir / "final" / "video.ffprobe.json").write_text(json.dumps(ffprobe_json(final_video), indent=2), encoding="utf-8")
    receipts.log("audio_retry_remux", status="pass", final_video=str(final_video), audio=str(audio), backup=str(backup))
    return final_video


def retry_audio_proof(run_dir: Path, *, local_only: bool = False, cloud_budget_usd: float = 25.0) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    receipts = Receipts(run_dir / "receipts.jsonl")
    if not run_dir.exists():
        raise FileNotFoundError(f"run directory not found: {run_dir}")
    if not receipts.path.exists():
        raise FileNotFoundError(f"receipts not found: {receipts.path}")

    source_audio = run_dir / "audio" / "source-audio.wav"
    if not source_audio.exists():
        receipts.log("blocker", code="audio_extract_missing_for_retry", expected=str(source_audio))
        raise RuntimeError("audio_extract_missing_for_retry")

    receipts.log("audio_proof_retry", status="start", source_audio=str(source_audio), local_only=local_only, cloud_budget_usd=cloud_budget_usd)
    _verify_source_manifest(run_dir, receipts)

    rows_before = receipts.read_all()
    cost = CostTracker(receipts, cap_usd=cloud_budget_usd, spent_usd=_latest_cost_spent(rows_before))
    policy = RunPolicy(local_only=local_only, cloud_budget_usd=cloud_budget_usd)
    selected_audio = polish_extracted_audio(source_audio, run_dir, receipts, policy, cost, allow_local_fallback=False)
    if selected_audio is not None:
        try:
            _remux_final_video(run_dir, selected_audio, receipts)
        except Exception as exc:
            receipts.log("audio_polish", status="failed", reason="final_video_remux_failed", error=str(exc))

    audio_proof_path = write_audio_proof(run_dir, receipts)
    proof = read_json_object(audio_proof_path) or {}
    cost_summary = CostTracker(receipts, cap_usd=cloud_budget_usd, spent_usd=_latest_cost_spent(receipts.read_all())).summary()

    _refresh_json_audio(run_dir / "scorecard.json", audio_proof_path, proof, cost_summary)
    _refresh_json_audio(run_dir / "final" / "launch-kit" / "launch-kit.json", audio_proof_path, proof, cost_summary)
    _refresh_json_audio(run_dir / "final" / "review" / "review-packet.json", audio_proof_path, proof, cost_summary)
    _rewrite_line(run_dir / "scorecard.md", "- cost:", f"- cost: ${cost_summary['spent_usd']:.4f} / ${cost_summary['cap_usd']:.2f}")
    _rewrite_line(run_dir / "scorecard.md", "- audio_quality:", f"- audio_quality: {proof.get('quality_status', 'missing')}")
    _rewrite_line(run_dir / "final" / "review" / "review-packet.md", "- audio_quality:", f"- audio_quality: {proof.get('quality_status', 'missing')}")

    status = "pass" if proof.get("strong_studio_sound") is True else "blocked"
    result = {
        "run_dir": str(run_dir),
        "status": status,
        "audio_proof": str(audio_proof_path),
        "quality_status": proof.get("quality_status"),
        "strong_studio_sound": proof.get("strong_studio_sound"),
        "quality_blockers": proof.get("quality_blockers") or [],
        "cost": cost_summary,
    }
    receipts.log("audio_proof_retry", **result)
    return result
