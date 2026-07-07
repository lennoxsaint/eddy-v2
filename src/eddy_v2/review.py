from __future__ import annotations

import html
import json
import os
import shlex
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


def _extract_clip(video: Path, output: Path, start_s: float, duration_s: float, receipts: Receipts, *, scale: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{max(0.0, start_s):.3f}",
            "-i",
            str(video),
            "-t",
            f"{max(0.25, duration_s):.3f}",
            "-vf",
            f"scale={scale}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output),
        ],
        receipts,
        event="ffmpeg",
        timeout_s=300,
    )


def _concat_clips(clips: list[Path], output: Path, receipts: Receipts) -> Path | None:
    if not clips:
        return None
    output.parent.mkdir(parents=True, exist_ok=True)
    list_path = output.with_suffix(".txt")
    list_path.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clips), encoding="utf-8")
    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ],
        receipts,
        event="ffmpeg",
        timeout_s=300,
    )
    return output


def _build_long_review_reel(long_video: Path, duration: float, review_dir: Path, receipts: Receipts) -> Path | None:
    clip_duration = min(5.0, max(0.5, duration))
    clips: list[Path] = []
    for index, at_s in enumerate(_long_sample_times(duration), start=1):
        start_s = min(max(0.0, at_s - (clip_duration / 2)), max(0.0, duration - clip_duration))
        clip = review_dir / "reels" / f"long-clip-{index:02d}.mp4"
        _extract_clip(long_video, clip, start_s, clip_duration, receipts, scale="960:-2")
        clips.append(clip)
    return _concat_clips(clips, review_dir / "reels" / "long-review-reel.mp4", receipts)


def _build_shorts_review_reel(shorts: list[Path], review_dir: Path, receipts: Receipts) -> Path | None:
    clips: list[Path] = []
    for index, short in enumerate(shorts, start=1):
        clip = review_dir / "reels" / f"short-{index:02d}-clip.mp4"
        _extract_clip(short, clip, 0.0, min(10.0, max(0.5, _duration(short))), receipts, scale="540:960")
        clips.append(clip)
    return _concat_clips(clips, review_dir / "reels" / "shorts-review-reel.mp4", receipts)


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


def _relpath(from_dir: Path, target: str | None) -> str | None:
    if not target:
        return None
    return os.path.relpath(target, from_dir)


def _review_command(run_dir: Path) -> str:
    quoted = shlex.quote(str(run_dir))
    return f"eddy review {quoted} --long-edit 8 --motion 8 --audio 8 --shorts 8"


def _write_review_html(review_dir: Path, packet: dict[str, Any]) -> Path:
    reels_raw = packet.get("review_reels")
    reels = reels_raw if isinstance(reels_raw, dict) else {}
    long_reel = _relpath(review_dir, reels.get("long"))
    shorts_reel = _relpath(review_dir, reels.get("shorts"))
    long_video = _relpath(review_dir, str(packet.get("long_video") or ""))
    shorts = [_relpath(review_dir, str(path)) for path in packet.get("shorts", [])]
    command = html.escape(str(packet.get("review_command") or ""))
    audio_quality = html.escape(str((packet.get("audio_proof") or {}).get("quality_status", "missing")))
    criteria = "\n".join(
        f"<li>{html.escape(str(row['name']))}: needs {html.escape(str(row['required_score']))}/10+</li>"
        for row in packet.get("criteria", [])
    )
    short_links = "\n".join(
        f'<li><a href="{html.escape(str(path))}">{html.escape(Path(str(path)).name)}</a></li>'
        for path in shorts
        if path
    )
    long_video_block = (
        f'<video controls preload="metadata" src="{html.escape(long_reel)}"></video>'
        if long_reel
        else '<p class="missing">Long review reel missing.</p>'
    )
    shorts_video_block = (
        f'<video controls preload="metadata" src="{html.escape(shorts_reel)}"></video>'
        if shorts_reel
        else '<p class="missing">Shorts review reel missing.</p>'
    )
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Eddy V2 Review</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; max-width: 1120px; color: #111827; background: #f8fafc; }}
    h1, h2 {{ margin-bottom: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }}
    section {{ background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; }}
    video {{ width: 100%; max-height: 520px; background: #020617; border-radius: 6px; }}
    code {{ display: block; white-space: pre-wrap; background: #111827; color: #f9fafb; padding: 12px; border-radius: 6px; }}
    .missing {{ color: #b91c1c; }}
  </style>
</head>
<body>
  <h1>Eddy V2 Review</h1>
  <p>Status: {html.escape(str(packet.get("status", "unknown")))}. Audio: {audio_quality}.</p>
  <div class="grid">
    <section>
      <h2>Long Reel</h2>
      {long_video_block}
      <p><a href="{html.escape(str(long_video))}">Open final long video</a></p>
    </section>
    <section>
      <h2>Shorts Reel</h2>
      {shorts_video_block}
      <ul>{short_links}</ul>
    </section>
  </div>
  <section>
    <h2>Score Gate</h2>
    <ul>{criteria}</ul>
    <code>{command}</code>
  </section>
</body>
</html>
"""
    path = review_dir / "review.html"
    path.write_text(page, encoding="utf-8")
    return path


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

        long_reel = _build_long_review_reel(long_video, long_duration, review_dir, receipts)
        shorts_reel = _build_shorts_review_reel(shorts, review_dir, receipts)

        packet = {
            "status": "pending_lennox_review",
            "winner_bar": "Lennox would publish it; long edit, motion, audio, and Shorts are each 8/10+.",
            "publishable_8_of_10": False,
            "long_video": str(long_video),
            "shorts": [str(path) for path in shorts],
            "review_command": _review_command(run_dir),
            "review_reels": {
                "long": str(long_reel) if long_reel else None,
                "shorts": str(shorts_reel) if shorts_reel else None,
            },
            "long_samples": long_samples,
            "short_samples": short_samples,
            "audio_proof_path": str(audio_proof) if audio_proof else None,
            "audio_proof": read_json_object(audio_proof),
            "criteria": _criterion_rows(),
        }
        review_dir.mkdir(parents=True, exist_ok=True)
        packet["review_page"] = str(review_dir / "review.html")
        review_page = _write_review_html(review_dir, packet)
        packet["review_page"] = str(review_page)
        packet_path = review_dir / "review-packet.json"
        packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
        (review_dir / "README.md").write_text(_markdown(packet), encoding="utf-8")
        receipts.log(
            "review_packet",
            status="pass",
            packet=str(packet_path),
            long_sample_count=len(long_samples),
            short_sample_count=len(short_samples),
            long_review_reel=str(long_reel) if long_reel else None,
            shorts_review_reel=str(shorts_reel) if shorts_reel else None,
            review_page=str(review_page),
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
    reels_raw = packet.get("review_reels")
    reels: dict[str, Any] = reels_raw if isinstance(reels_raw, dict) else {}
    lines.extend(["", "## Review Reels", ""])
    if reels.get("long"):
        lines.append(f"- long: {reels['long']}")
    if reels.get("shorts"):
        lines.append(f"- shorts: {reels['shorts']}")
    lines.extend(["", "## Long Samples", ""])
    for sample in packet["long_samples"]:
        lines.append(f"- {sample['time_s']}s: {sample['path']}")
    lines.extend(["", "## Shorts Samples", ""])
    for sample in packet["short_samples"]:
        lines.append(f"- {Path(sample['short']).name} at {sample['time_s']}s: {sample['path']}")
    lines.append("")
    return "\n".join(lines)
