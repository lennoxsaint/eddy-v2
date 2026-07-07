from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .commands import ffprobe_json, run_command
from .proof import read_json_object
from .receipts import Receipts


def _duration(path: Path) -> float:
    probe = ffprobe_json(path)
    value = probe.get("format", {}).get("duration") or 0
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _extract_frame(video: Path, output: Path, at_s: float, receipts: Receipts) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{max(0.0, at_s):.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-update",
            "1",
            "-vf",
            "scale=480:-1",
            str(output),
        ],
        receipts,
        event="ffmpeg",
        timeout_s=300,
    )


def _long_sample_times(duration: float) -> list[float]:
    if duration <= 0:
        return [0.0]
    return sorted({round(min(max(duration * fraction, 0.0), max(duration - 0.1, 0.0)), 3) for fraction in (0.05, 0.25, 0.5, 0.75, 0.95)})


def _criterion_rows() -> list[dict[str, Any]]:
    return [
        {"name": "long_edit_story", "required_score": 8, "status": "pending_lennox_review"},
        {"name": "motion_graphics", "required_score": 8, "status": "pending_lennox_review"},
        {"name": "audio_polish", "required_score": 8, "status": "pending_lennox_review"},
        {"name": "shorts_watchability", "required_score": 8, "status": "pending_lennox_review"},
    ]


def build_review_packet(run_dir: Path, long_video: Path, shorts: list[Path], receipts: Receipts, *, audio_proof: Path | None = None) -> Path | None:
    review_dir = run_dir / "final" / "review"
    try:
        long_duration = _duration(long_video)
        long_samples: list[dict[str, Any]] = []
        for index, at_s in enumerate(_long_sample_times(long_duration), start=1):
            output = review_dir / "frames" / f"long-{index:02d}.png"
            _extract_frame(long_video, output, at_s, receipts)
            long_samples.append({"time_s": at_s, "path": str(output)})

        short_samples: list[dict[str, Any]] = []
        for index, short in enumerate(shorts, start=1):
            duration = _duration(short)
            at_s = round(max(0.0, min(duration / 2, max(duration - 0.1, 0.0))), 3)
            output = review_dir / "frames" / f"short-{index:02d}.png"
            _extract_frame(short, output, at_s, receipts)
            short_samples.append({"short": str(short), "time_s": at_s, "path": str(output)})

        packet = {
            "status": "pending_lennox_review",
            "winner_bar": "Lennox would publish it; long edit, motion, audio, and Shorts are each 8/10+.",
            "publishable_8_of_10": False,
            "long_video": str(long_video),
            "shorts": [str(path) for path in shorts],
            "long_samples": long_samples,
            "short_samples": short_samples,
            "audio_proof_path": str(audio_proof) if audio_proof else None,
            "audio_proof": read_json_object(audio_proof),
            "criteria": _criterion_rows(),
        }
        review_dir.mkdir(parents=True, exist_ok=True)
        packet_path = review_dir / "review-packet.json"
        packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
        (review_dir / "README.md").write_text(_markdown(packet), encoding="utf-8")
        receipts.log(
            "review_packet",
            status="pass",
            packet=str(packet_path),
            long_sample_count=len(long_samples),
            short_sample_count=len(short_samples),
        )
        return packet_path
    except Exception as exc:
        receipts.log("review_packet", status="failed", error=str(exc), review_dir=str(review_dir))
        return None


def _markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# Eddy V2 Review Packet",
        "",
        f"- status: {packet['status']}",
        f"- long_video: {packet['long_video']}",
        f"- shorts_count: {len(packet['shorts'])}",
        f"- publishable_8_of_10: {str(packet['publishable_8_of_10']).lower()}",
        f"- winner_bar: {packet['winner_bar']}",
        f"- audio_quality: {(packet.get('audio_proof') or {}).get('quality_status', 'missing')}",
        "",
        "## Review Criteria",
        "",
    ]
    for criterion in packet["criteria"]:
        lines.append(f"- {criterion['name']}: pending Lennox score >= {criterion['required_score']}/10")
    lines.extend(["", "## Long Samples", ""])
    for sample in packet["long_samples"]:
        lines.append(f"- {sample['time_s']}s: {sample['path']}")
    lines.extend(["", "## Shorts Samples", ""])
    for sample in packet["short_samples"]:
        lines.append(f"- {Path(sample['short']).name} at {sample['time_s']}s: {sample['path']}")
    lines.append("")
    return "\n".join(lines)
