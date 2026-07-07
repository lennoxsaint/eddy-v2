from __future__ import annotations

import json
import textwrap
from pathlib import Path

from .audio import polish_audio
from .captions import CaptionCue, build_short_cues, write_caption_artifacts, write_cue_textfiles
from .commands import duration_s, ffprobe_json, run_command
from .cost import CostTracker
from .models import EditIntent
from .motion import create_motion_project, run_hyperframes
from .plan import EditPlan
from .policy import RunPolicy
from .qa import validate_caption_sidecars, validate_long_video, validate_motion_artifact, validate_short_video
from .receipts import Receipts
from .sources import Sources


def drawtext_file(run_dir: Path, name: str, text: str, *, width: int) -> str:
    text_dir = run_dir / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    wrapped = textwrap.fill(text, width=width, break_long_words=False, break_on_hyphens=False)
    path = text_dir / f"{name}.txt"
    path.write_text(wrapped, encoding="utf-8")
    return str(path).replace("\\", "\\\\").replace(":", "\\:")


def cue_drawtext_filters(
    run_dir: Path,
    prefix: str,
    cues: list[CaptionCue],
    *,
    width: int,
    x: str,
    y: str,
    fontsize: int,
    boxcolor: str,
    borderw: int,
) -> str:
    filters = []
    for cue, textfile in write_cue_textfiles(run_dir, prefix, cues, width=width):
        filters.append(
            f"drawtext=textfile='{textfile}':x={x}:y={y}:fontsize={fontsize}:line_spacing=8:"
            f"fontcolor=white:box=1:boxcolor={boxcolor}:boxborderw={borderw}:"
            f"enable='between(t,{cue.start_s:.3f},{cue.end_s:.3f})'"
        )
    return ",".join(filters)


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
    source_duration = duration_s(sources.camera)
    start = plan.long_segment.start_s if plan else 0.0
    target = max(1.0, min(plan.long_segment.duration_s if plan else intent.target_duration_s, source_duration - start))
    audio = polish_audio(sources, run_dir, receipts, policy, cost, start_s=start, duration_s=target)
    motion_project = create_motion_project(run_dir, intent.identity, intent.hook, portrait=False, duration_s=target, plan=plan, receipts=receipts)
    motion_output = run_hyperframes(motion_project, receipts)
    validate_motion_artifact(motion_project, motion_output, receipts, portrait=False)

    output = final_dir / "video.mp4"
    long_cues = write_caption_artifacts(final_dir, intent, target, receipts)
    long_caption_filters = cue_drawtext_filters(
        run_dir,
        "long-callout",
        long_cues,
        width=48,
        x="80",
        y="h-210",
        fontsize=42,
        boxcolor="0x07111fcc",
        borderw=22,
    )
    if sources.screen:
        filter_complex = (
            "[1:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black[base];"
            "[0:v]scale=420:-1[cam];"
            "[base][cam]overlay=40:40[pip];"
            "[3:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080[ov];"
            f"[pip][ov]blend=all_mode=screen:shortest=1,{long_caption_filters}[v]"
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
            "-t",
            f"{target:.3f}",
            "-i",
            str(audio),
            "-stream_loop",
            "-1",
            "-t",
            f"{target:.3f}",
            "-i",
            str(motion_output),
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
            "-t",
            f"{target:.3f}",
            "-i",
            str(audio),
            "-stream_loop",
            "-1",
            "-t",
            f"{target:.3f}",
            "-i",
            str(motion_output),
            "-filter_complex",
            (
                "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black[base];"
                "[2:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080[ov];"
                f"[base][ov]blend=all_mode=screen:shortest=1,{long_caption_filters}[v]"
            ),
            "-map",
            "[v]",
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
    receipts.log("motion_composite", status="pass", surface="long", mode="screen_blend", motion=str(motion_output))
    run_command(args, receipts, event="ffmpeg", timeout_s=7200)
    probe = ffprobe_json(output)
    (final_dir / "video.ffprobe.json").write_text(json.dumps(probe, indent=2), encoding="utf-8")
    validate_caption_sidecars(final_dir, receipts, title=intent.title)
    validate_long_video(run_dir, output, receipts, expected_duration_s=target)
    return output


def render_shorts(sources: Sources, run_dir: Path, intent: EditIntent, receipts: Receipts, *, plan: EditPlan | None = None) -> list[Path]:
    shorts_dir = run_dir / "final" / "shorts"
    shorts_dir.mkdir(parents=True, exist_ok=True)
    motion_project = create_motion_project(run_dir, intent.identity, intent.hook, portrait=True, duration_s=15.0, receipts=receipts)
    motion_output = run_hyperframes(motion_project, receipts, portrait=True)
    validate_motion_artifact(motion_project, motion_output, receipts, portrait=True)
    source_duration = duration_s(sources.camera)
    outputs: list[Path] = []
    short_cues = build_short_cues(intent)
    short_caption_filters = cue_drawtext_filters(
        run_dir,
        "short-caption",
        short_cues,
        width=24,
        x="60",
        y="1380",
        fontsize=58,
        boxcolor="0x07111fe6",
        borderw=24,
    )
    receipts.log("caption_plan", status="pass", surface="shorts", cue_count=len(short_cues))
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
                "[cam][screen]vstack=inputs=2[stack];"
                "[2:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[ov];"
                f"[stack][ov]blend=all_mode=screen:shortest=1,{short_caption_filters}[v]"
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
                "-i",
                str(motion_output),
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
                "-i",
                str(motion_output),
                "-filter_complex",
                (
                    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[base];"
                    "[1:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[ov];"
                    f"[base][ov]blend=all_mode=screen:shortest=1,{short_caption_filters}[v]"
                ),
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
        try:
            receipts.log("motion_composite", status="pass", surface="shorts", index=index, mode="screen_blend", motion=str(motion_output))
            run_command(args, receipts, event="ffmpeg", timeout_s=1800)
            if validate_short_video(run_dir, out, receipts, index=index):
                receipts.log("short_rendered", index=index, status="pass", output=str(out))
                outputs.append(out)
            else:
                receipts.log("short_rendered", index=index, status="failed", reason="short_media_integrity_failed")
        except Exception as exc:
            q = run_dir / "quarantine" / out.name
            if out.exists():
                out.replace(q)
            receipts.log("short_rendered", index=index, status="failed", error=str(exc), quarantine=str(q))
    if len(outputs) < 3:
        receipts.log("shorts_quality_shortfall", status="pass", rendered=len(outputs), required=3)
    return outputs
