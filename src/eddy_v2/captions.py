from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import EditIntent
from .receipts import Receipts


@dataclass(frozen=True)
class CaptionCue:
    start_s: float
    end_s: float
    text: str
    kind: str

    def as_dict(self) -> dict:
        return {
            "start_s": round(self.start_s, 3),
            "end_s": round(self.end_s, 3),
            "text": self.text,
            "kind": self.kind,
        }


def _time_srt(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _time_vtt(seconds: float) -> str:
    return _time_srt(seconds).replace(",", ".")


def _add_cue(cues: list[CaptionCue], start: float, end: float, text: str, kind: str, duration: float) -> None:
    clipped_start = max(0.0, min(start, duration))
    clipped_end = max(0.0, min(end, duration))
    if clipped_end - clipped_start >= 0.75 and text.strip():
        cues.append(CaptionCue(clipped_start, clipped_end, text.strip(), kind))


def build_long_cues(intent: EditIntent, duration: float) -> list[CaptionCue]:
    cues: list[CaptionCue] = []
    _add_cue(cues, 0.0, min(6.0, duration), intent.hook, "hook", duration)
    _add_cue(cues, 8.0, 15.0, "Source-safe edit: raw files stay untouched", "callout", duration)
    _add_cue(cues, 22.0, 30.0, "Receipts track every model, render, and gate", "callout", duration)
    _add_cue(cues, 38.0, 46.0, "Shorts are counted only after QA passes", "callout", duration)
    if duration >= 20.0:
        _add_cue(cues, max(0.0, duration - 8.0), duration, intent.title, "title", duration)
    return cues


def build_short_cues(intent: EditIntent, duration: float = 15.0) -> list[CaptionCue]:
    hook_words = intent.hook.split()
    first = " ".join(hook_words[:6]) if hook_words else intent.title
    second = " ".join(hook_words[6:12]) if len(hook_words) > 6 else "Proof-gated, not vibes"
    cues: list[CaptionCue] = []
    _add_cue(cues, 0.0, 4.5, first, "kinetic_caption", duration)
    _add_cue(cues, 4.5, 9.5, second, "kinetic_caption", duration)
    _add_cue(cues, 9.5, 14.5, "Receipts before final", "kinetic_caption", duration)
    return cues


def _read_json_object(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    parsed = json.loads(path.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, dict) else None


def _timeline_cues_from_transcript(
    transcript_cues_path: Path | None,
    source_segments: list[dict[str, float]] | None,
    duration: float,
) -> list[CaptionCue]:
    payload = _read_json_object(transcript_cues_path)
    if not payload or not source_segments:
        return []
    raw_cues = payload.get("cues")
    if not isinstance(raw_cues, list):
        return []

    segments: list[tuple[float, float, float]] = []
    cursor = 0.0
    for segment in source_segments:
        try:
            start = float(segment["start_s"])
            segment_duration = float(segment["duration_s"])
        except (KeyError, TypeError, ValueError):
            continue
        if segment_duration <= 0:
            continue
        segments.append((start, start + segment_duration, cursor))
        cursor += segment_duration

    cues: list[CaptionCue] = []
    for raw in raw_cues:
        if not isinstance(raw, dict):
            continue
        try:
            cue_start = float(raw["start_s"])
            cue_end = float(raw["end_s"])
        except (KeyError, TypeError, ValueError):
            continue
        text = str(raw.get("text") or "").strip()
        for segment_start, segment_end, timeline_start in segments:
            overlap_start = max(cue_start, segment_start)
            overlap_end = min(cue_end, segment_end)
            if overlap_end <= overlap_start:
                continue
            _add_cue(
                cues,
                timeline_start + (overlap_start - segment_start),
                timeline_start + (overlap_end - segment_start),
                text,
                "transcript",
                duration,
            )
    cues.sort(key=lambda cue: (cue.start_s, cue.end_s, cue.text))
    return cues


def caption_provenance_payload(
    cues: list[CaptionCue],
    *,
    transcript_cue_count: int = 0,
    sidecar_source: str = "editorial_callouts",
    transcript_source: str | None = None,
) -> dict:
    speech_accurate = sidecar_source == "transcript" and bool(cues)
    return {
        "status": "pass" if speech_accurate else "warning",
        "sidecar_source": sidecar_source,
        "caption_kinds": sorted({cue.kind for cue in cues}),
        "cue_count": len(cues),
        "transcript_available": transcript_cue_count > 0,
        "transcript_cue_count": transcript_cue_count,
        "transcript_source": transcript_source,
        "speech_accurate_subtitles": speech_accurate,
        "warning": None if speech_accurate else "speech_accurate_subtitles_not_proven",
    }


def write_caption_provenance(
    final_dir: Path,
    cues: list[CaptionCue],
    receipts: Receipts | None = None,
    *,
    transcript_cue_count: int = 0,
    sidecar_source: str = "editorial_callouts",
    transcript_source: str | None = None,
) -> dict:
    provenance = caption_provenance_payload(
        cues,
        transcript_cue_count=transcript_cue_count,
        sidecar_source=sidecar_source,
        transcript_source=transcript_source,
    )
    provenance_path = final_dir / "caption-provenance.json"
    provenance_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    if receipts:
        receipts.log("caption_provenance", output=str(provenance_path), **provenance)
    return provenance


def write_caption_artifacts(
    final_dir: Path,
    intent: EditIntent,
    duration: float,
    receipts: Receipts,
    *,
    transcript_cue_count: int = 0,
    transcript_cues_path: Path | None = None,
    source_segments: list[dict[str, float]] | None = None,
) -> list[CaptionCue]:
    visual_cues = build_long_cues(intent, duration)
    transcript_cues = _timeline_cues_from_transcript(transcript_cues_path, source_segments, duration)
    sidecar_cues = transcript_cues or visual_cues
    sidecar_source = "transcript" if transcript_cues else "editorial_callouts"
    transcript_payload = _read_json_object(transcript_cues_path)
    transcript_source = str(transcript_payload.get("source")) if transcript_payload and transcript_payload.get("source") else None
    payload = {
        "cues": [cue.as_dict() for cue in sidecar_cues],
        "visual_callouts": [cue.as_dict() for cue in visual_cues],
    }
    (final_dir / "captions.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    srt_blocks = []
    vtt_blocks = ["WEBVTT", ""]
    for index, cue in enumerate(sidecar_cues, start=1):
        wrapped = textwrap.fill(cue.text, width=48, break_long_words=False, break_on_hyphens=False)
        srt_blocks.append(f"{index}\n{_time_srt(cue.start_s)} --> {_time_srt(cue.end_s)}\n{wrapped}\n")
        vtt_blocks.append(f"{_time_vtt(cue.start_s)} --> {_time_vtt(cue.end_s)}\n{wrapped}\n")
    (final_dir / "subtitles.srt").write_text("\n".join(srt_blocks), encoding="utf-8")
    (final_dir / "subtitles.vtt").write_text("\n".join(vtt_blocks), encoding="utf-8")
    provenance = write_caption_provenance(
        final_dir,
        sidecar_cues,
        receipts,
        transcript_cue_count=transcript_cue_count,
        sidecar_source=sidecar_source,
        transcript_source=transcript_source,
    )
    receipts.log(
        "caption_plan",
        status="pass",
        cue_count=len(sidecar_cues),
        visual_cue_count=len(visual_cues),
        output=str(final_dir / "captions.json"),
        sidecar_source=provenance["sidecar_source"],
        speech_accurate_subtitles=provenance["speech_accurate_subtitles"],
    )
    return visual_cues


def write_cue_textfiles(run_dir: Path, prefix: str, cues: list[CaptionCue], *, width: int) -> list[tuple[CaptionCue, str]]:
    text_dir = run_dir / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[CaptionCue, str]] = []
    for index, cue in enumerate(cues):
        path = text_dir / f"{prefix}-{index:02d}.txt"
        path.write_text(textwrap.fill(cue.text, width=width, break_long_words=False, break_on_hyphens=False), encoding="utf-8")
        written.append((cue, str(path).replace("\\", "\\\\").replace(":", "\\:")))
    return written
