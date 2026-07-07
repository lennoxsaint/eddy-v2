from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .commands import ffprobe_json, run_command
from .plan import EditPlan
from .receipts import Receipts


def _video_stream(probe: dict[str, Any]) -> dict[str, Any] | None:
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    return None


def _duration_s(probe: dict[str, Any], stream: dict[str, Any] | None) -> float:
    value = probe.get("format", {}).get("duration") or (stream or {}).get("duration") or 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _quarantine(path: Path, run_dir: Path, receipts: Receipts, *, gate: str, reason: str) -> None:
    quarantine_dir = run_dir / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    target = quarantine_dir / path.name
    if path.exists():
        path.replace(target)
    receipts.log("gate", name=gate, status="failed", reason=reason, output=str(path), quarantine=str(target))


def validate_cut_integrity(
    plan: EditPlan,
    receipts: Receipts,
    *,
    short_duration_s: float = 15.0,
    min_short_gap_s: float = 15.0,
) -> None:
    gate = "cut_integrity"
    reasons: list[str] = []
    source_duration = plan.source_duration_s
    long_segments = plan.source_segments()
    if source_duration <= 0:
        reasons.append("source_duration_invalid")
    prior_end = -1.0
    for index, segment in enumerate(long_segments):
        prefix = "long_segment" if len(long_segments) == 1 else f"long_segment_{index + 1:02d}"
        long_start = segment.start_s
        long_duration = segment.duration_s
        long_end = segment.end_s
        if long_start < 0:
            reasons.append(f"{prefix}_negative_start")
        if long_duration <= 0:
            reasons.append(f"{prefix}_nonpositive_duration")
        if long_end > source_duration + 0.75:
            reasons.append(f"{prefix}_exceeds_source")
        if long_start < prior_end - 0.001:
            reasons.append("long_segments_overlap_or_out_of_order")
        prior_end = max(prior_end, long_end)
    for index, start in enumerate(plan.short_starts_s):
        if start < 0:
            reasons.append(f"short_{index + 1:02d}_negative_start")
        if start + short_duration_s > source_duration + 0.75:
            reasons.append(f"short_{index + 1:02d}_exceeds_source")
    starts = sorted(plan.short_starts_s)
    for index, start in enumerate(starts[:-1]):
        if starts[index + 1] - start < min_short_gap_s:
            reasons.append("short_starts_too_close")
            break
    for index, (start, end) in enumerate(plan.non_silent_intervals):
        if start < 0 or end > source_duration + 0.75 or end <= start:
            reasons.append(f"non_silent_interval_{index + 1:02d}_out_of_bounds")
            break
    payload = {
        "source_duration_s": round(source_duration, 3),
        "long_segment": plan.long_segment.as_dict(),
        "long_segments": [segment.as_dict() for segment in long_segments],
        "long_duration_s": round(plan.long_duration_s, 3),
        "short_starts_s": [round(start, 3) for start in plan.short_starts_s],
        "short_count": len(plan.short_starts_s),
    }
    if reasons:
        receipts.log("gate", name=gate, status="failed", reasons=sorted(set(reasons)), **payload)
        raise RuntimeError("cut_integrity_failed")
    receipts.log("gate", name=gate, status="pass", **payload)


def validate_long_video(run_dir: Path, output: Path, receipts: Receipts, *, expected_duration_s: float) -> None:
    gate = "long_media_integrity"
    if not output.exists():
        receipts.log("gate", name=gate, status="failed", reason="missing_long_video", output=str(output))
        raise RuntimeError("missing_long_video")
    try:
        probe = ffprobe_json(output)
    except Exception as exc:
        _quarantine(output, run_dir, receipts, gate=gate, reason=f"ffprobe_failed:{exc}")
        raise RuntimeError("final_media_corrupt") from exc
    stream = _video_stream(probe)
    duration = _duration_s(probe, stream)
    if not stream:
        _quarantine(output, run_dir, receipts, gate=gate, reason="missing_video_stream")
        raise RuntimeError("final_media_corrupt")
    if (stream.get("width"), stream.get("height")) != (1920, 1080):
        _quarantine(output, run_dir, receipts, gate=gate, reason="unexpected_long_geometry")
        raise RuntimeError("final_media_corrupt")
    if duration <= 0 or duration + 0.75 < expected_duration_s:
        _quarantine(output, run_dir, receipts, gate=gate, reason="unexpected_long_duration")
        raise RuntimeError("final_media_corrupt")
    receipts.log(
        "gate",
        name=gate,
        status="pass",
        output=str(output),
        width=stream.get("width"),
        height=stream.get("height"),
        duration_s=round(duration, 3),
    )


def validate_caption_sidecars(final_dir: Path, receipts: Receipts, *, title: str) -> None:
    missing_or_empty = []
    for name in ("captions.json", "subtitles.srt", "subtitles.vtt"):
        path = final_dir / name
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            missing_or_empty.append(name)
    if missing_or_empty:
        receipts.log("gate", name="caption_sidecars", status="failed", missing=missing_or_empty)
        raise RuntimeError(f"caption_sidecars_corrupt:{','.join(missing_or_empty)}")
    captions = json.loads((final_dir / "captions.json").read_text(encoding="utf-8"))
    cues = captions.get("cues") if isinstance(captions.get("cues"), list) else []
    if not cues:
        receipts.log("gate", name="caption_sidecars", status="failed", reason="no_cues")
        raise RuntimeError("caption_sidecars_corrupt:no_cues")
    receipts.log("gate", name="caption_sidecars", status="pass", files=["captions.json", "subtitles.srt", "subtitles.vtt"], title=title, cue_count=len(cues))


def validate_motion_artifact(project: Path, output: Path, receipts: Receipts, *, portrait: bool) -> None:
    gate = "motion_artifact"
    required_files = [
        "frame.md",
        "storyboard.md",
        "storyboard.html",
        "identity.css",
        "blocks.json",
        "index.html",
        "motion-plan.json",
        "motion-collision-proof.json",
        "motion-lint.json",
        "motion-inspect.json",
    ]
    missing = [name for name in required_files if not (project / name).exists()]
    if missing:
        receipts.log("gate", name=gate, status="failed", reason="missing_motion_project_files", missing=missing, project=str(project))
        raise RuntimeError("motion_artifact_corrupt")
    if not output.exists():
        receipts.log("gate", name=gate, status="failed", reason="missing_motion_render", output=str(output), project=str(project))
        raise RuntimeError("motion_artifact_corrupt")
    probe = ffprobe_json(output)
    stream = _video_stream(probe)
    expected = (1080, 1920) if portrait else (1920, 1080)
    if not stream or (stream.get("width"), stream.get("height")) != expected:
        receipts.log("gate", name=gate, status="failed", reason="unexpected_motion_geometry", output=str(output), expected=expected)
        raise RuntimeError("motion_artifact_corrupt")
    collision = json.loads((project / "motion-collision-proof.json").read_text(encoding="utf-8"))
    if collision.get("status") != "pass":
        receipts.log("gate", name="motion_collision_proof", status="failed", project=str(project), proof=collision)
        raise RuntimeError("motion_collision_proof_failed")
    receipts.log(
        "gate",
        name="motion_collision_proof",
        status="pass",
        project=str(project),
        check_count=len(collision.get("checks", [])),
    )
    receipts.log("gate", name=gate, status="pass", output=str(output), project=str(project), width=stream.get("width"), height=stream.get("height"))
    validate_motion_visual_qa(output, project, receipts)


def validate_motion_visual_qa(output: Path, project: Path, receipts: Receipts) -> None:
    proc = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(output),
            "-vf",
            "fps=1,scale=16:16,format=gray",
            "-f",
            "framemd5",
            "-",
        ],
        receipts,
        event="ffmpeg",
        timeout_s=300,
        check=False,
    )
    hashes = []
    for line in proc.stdout.splitlines():
        if line.startswith("#") or "," not in line:
            continue
        hashes.append(line.rsplit(",", 1)[-1].strip())
    unique_hashes = sorted(set(hashes))
    report = {
        "output": str(output),
        "sampled_frames": len(hashes),
        "unique_frame_hashes": len(unique_hashes),
        "inspect_file": str(project / "motion-inspect.json"),
    }
    (project / "motion-visual-qa.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if proc.returncode != 0 or len(hashes) < 2 or len(unique_hashes) < 2:
        receipts.log("gate", name="motion_visual_qa", status="failed", **report)
        raise RuntimeError("motion_visual_qa_failed")
    receipts.log("gate", name="motion_visual_qa", status="pass", **report)


def validate_short_video(run_dir: Path, output: Path, receipts: Receipts, *, index: int) -> bool:
    gate = "short_media_integrity"
    if not output.exists():
        receipts.log("gate", name=gate, status="failed", index=index, reason="missing_short", output=str(output))
        return False
    try:
        probe = ffprobe_json(output)
    except Exception as exc:
        _quarantine(output, run_dir, receipts, gate=gate, reason=f"ffprobe_failed:{exc}")
        return False
    stream = _video_stream(probe)
    duration = _duration_s(probe, stream)
    if not stream or (stream.get("width"), stream.get("height")) != (1080, 1920):
        _quarantine(output, run_dir, receipts, gate=gate, reason="unexpected_short_geometry")
        return False
    if duration < 10.0:
        _quarantine(output, run_dir, receipts, gate=gate, reason="short_too_short")
        return False
    receipts.log(
        "gate",
        name=gate,
        status="pass",
        index=index,
        output=str(output),
        width=stream.get("width"),
        height=stream.get("height"),
        duration_s=round(duration, 3),
    )
    return True


def validate_launch_package(run_dir: Path, video: Path, shorts: list[Path], receipts: Receipts) -> None:
    kit = run_dir / "final" / "launch-kit"
    expected = [kit / "launch-kit.json", kit / "README.md", run_dir / "scorecard.json", run_dir / "scorecard.md", video]
    missing = [str(path) for path in expected if not path.exists()]
    if missing:
        receipts.log("gate", name="launch_package", status="failed", missing=missing)
        raise RuntimeError("launch_package_incomplete")
    receipts.log("gate", name="launch_package", status="pass", long_video=str(video), shorts=[str(path) for path in shorts])
