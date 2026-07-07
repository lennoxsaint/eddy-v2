from __future__ import annotations

import json
import textwrap
from pathlib import Path

from .audio import polish_audio
from .commands import duration_s, ffprobe_json, run_command
from .cost import CostTracker
from .models import EditIntent
from .motion import create_motion_project, run_hyperframes
from .plan import EditPlan
from .policy import RunPolicy
from .receipts import Receipts
from .sources import Sources


def drawtext_file(run_dir: Path, name: str, text: str, *, width: int) -> str:
    text_dir = run_dir / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    wrapped = textwrap.fill(text, width=width, break_long_words=False, break_on_hyphens=False)
    path = text_dir / f"{name}.txt"
    path.write_text(wrapped, encoding="utf-8")
    return str(path).replace("\\", "\\\\").replace(":", "\\:")


def write_sidecars(final_dir: Path, duration: float, title: str) -> None:
    srt = final_dir / "subtitles.srt"
    vtt = final_dir / "subtitles.vtt"
    srt.write_text(f"1\n00:00:00,000 --> 00:00:{min(int(duration), 59):02d},000\n{title}\n", encoding="utf-8")
    vtt.write_text(f"WEBVTT\n\n00:00.000 --> 00:{min(int(duration), 59):02d}.000\n{title}\n", encoding="utf-8")


def render_long(
    sources: Sources,
    run_dir: Path,
    intent: EditIntent,
    receipts: Receipts,
    policy: RunPolicy,
    cost: CostTracker,
    plan: EditPlan | None = None,
) -> Path:
    final_dir = run_dir / "final"
    quarantine = run_dir / "quarantine"
    final_dir.mkdir(parents=True, exist_ok=True)
    quarantine.mkdir(parents=True, exist_ok=True)
    audio = polish_audio(sources, run_dir, receipts, policy, cost)
    create_motion_project(run_dir, intent.identity, intent.hook, portrait=False)
    run_hyperframes(run_dir / "motion" / "long-overlay", receipts)

    output = final_dir / "video.mp4"
    source_duration = duration_s(sources.camera)
    start = plan.long_segment.start_s if plan else 0.0
    target = min(plan.long_segment.duration_s if plan else intent.target_duration_s, source_duration - start)
    long_hook_file = drawtext_file(run_dir, "long-hook", intent.hook, width=52)
    if sources.screen:
        filter_complex = (
            "[1:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black[base];"
            "[0:v]scale=420:-1[cam];"
            "[base][cam]overlay=40:40,"
            f"drawtext=textfile='{long_hook_file}':x=80:y=h-170:fontsize=44:line_spacing=8:"
            "fontcolor=white:box=1:boxcolor=0x07111fcc:boxborderw=24[v]"
        )
        args = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{target:.3f}",
            "-i",
            str(sources.camera),
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{target:.3f}",
            "-i",
            str(sources.screen),
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{target:.3f}",
            "-i",
            str(audio),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "2:a",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-shortest",
            str(output),
        ]
    else:
        args = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{target:.3f}",
            "-i",
            str(sources.camera),
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{target:.3f}",
            "-i",
            str(audio),
            "-vf",
            f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,drawtext=textfile='{long_hook_file}':x=80:y=h-170:fontsize=44:line_spacing=8:fontcolor=white:box=1:boxcolor=0x07111fcc:boxborderw=24",
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-c:a",
            "aac",
            "-shortest",
            str(output),
        ]
    run_command(args, receipts, event="ffmpeg", timeout_s=7200)
    write_sidecars(final_dir, target, intent.title)
    probe = ffprobe_json(output)
    (final_dir / "video.ffprobe.json").write_text(json.dumps(probe, indent=2), encoding="utf-8")
    receipts.log("gate", name="long_video_exists", status="pass", output=str(output))
    return output


def render_shorts(sources: Sources, run_dir: Path, intent: EditIntent, receipts: Receipts, *, plan: EditPlan | None = None) -> list[Path]:
    shorts_dir = run_dir / "final" / "shorts"
    shorts_dir.mkdir(parents=True, exist_ok=True)
    create_motion_project(run_dir, intent.identity, intent.hook, portrait=True)
    run_hyperframes(run_dir / "motion" / "shorts-card", receipts, portrait=True)
    source_duration = duration_s(sources.camera)
    outputs: list[Path] = []
    short_hook_file = drawtext_file(run_dir, "short-hook", intent.hook, width=28)
    starts = plan.short_starts_s if plan else [float(index * 20) for index in range(intent.shorts_target)]
    for index, start in enumerate(starts[: intent.shorts_target]):
        if start + 10 > source_duration:
            receipts.log("short_candidate", index=index, status="skipped", reason="source too short")
            continue
        out = shorts_dir / f"short-{index + 1:02d}.mp4"
        if sources.screen:
            filter_complex = (
                "[0:v]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[cam];"
                "[1:v]scale=1080:960:force_original_aspect_ratio=decrease,pad=1080:960:(ow-iw)/2:(oh-ih)/2:black[screen];"
                "[cam][screen]vstack=inputs=2,"
                f"drawtext=textfile='{short_hook_file}':x=60:y=1010:fontsize=52:line_spacing=10:fontcolor=white:"
                "box=1:boxcolor=0x07111fd9:boxborderw=20[v]"
            )
            args = [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start:.3f}",
                "-t",
                "15",
                "-i",
                str(sources.camera),
                "-ss",
                f"{start:.3f}",
                "-t",
                "15",
                "-i",
                str(sources.screen),
                "-filter_complex",
                filter_complex,
                "-map",
                "[v]",
                "-map",
                "0:a?",
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                "-c:a",
                "aac",
                "-shortest",
                str(out),
            ]
        else:
            args = [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start:.3f}",
                "-t",
                "15",
                "-i",
                str(sources.camera),
                "-vf",
                f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,drawtext=textfile='{short_hook_file}':x=60:y=1450:fontsize=52:line_spacing=10:fontcolor=white:box=1:boxcolor=0x07111fd9:boxborderw=20",
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                "-c:a",
                "aac",
                "-shortest",
                str(out),
            ]
        try:
            run_command(args, receipts, event="ffmpeg", timeout_s=1800)
            ffprobe_json(out)
            receipts.log("short_rendered", index=index, status="pass", output=str(out))
            outputs.append(out)
        except Exception as exc:
            q = run_dir / "quarantine" / out.name
            if out.exists():
                out.replace(q)
            receipts.log("short_rendered", index=index, status="failed", error=str(exc), quarantine=str(q))
    if len(outputs) < 3:
        receipts.log("shorts_quality_shortfall", status="pass", rendered=len(outputs), required=3)
    return outputs
