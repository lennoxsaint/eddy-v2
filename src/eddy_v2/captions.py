from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from pathlib import Path

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


def write_caption_artifacts(final_dir: Path, intent: EditIntent, duration: float, receipts: Receipts) -> list[CaptionCue]:
    cues = build_long_cues(intent, duration)
    payload = {"cues": [cue.as_dict() for cue in cues]}
    (final_dir / "captions.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    srt_blocks = []
    vtt_blocks = ["WEBVTT", ""]
    for index, cue in enumerate(cues, start=1):
        wrapped = textwrap.fill(cue.text, width=48, break_long_words=False, break_on_hyphens=False)
        srt_blocks.append(f"{index}\n{_time_srt(cue.start_s)} --> {_time_srt(cue.end_s)}\n{wrapped}\n")
        vtt_blocks.append(f"{_time_vtt(cue.start_s)} --> {_time_vtt(cue.end_s)}\n{wrapped}\n")
    (final_dir / "subtitles.srt").write_text("\n".join(srt_blocks), encoding="utf-8")
    (final_dir / "subtitles.vtt").write_text("\n".join(vtt_blocks), encoding="utf-8")
    receipts.log("caption_plan", status="pass", cue_count=len(cues), output=str(final_dir / "captions.json"))
    return cues


def write_cue_textfiles(run_dir: Path, prefix: str, cues: list[CaptionCue], *, width: int) -> list[tuple[CaptionCue, str]]:
    text_dir = run_dir / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    written: list[tuple[CaptionCue, str]] = []
    for index, cue in enumerate(cues):
        path = text_dir / f"{prefix}-{index:02d}.txt"
        path.write_text(textwrap.fill(cue.text, width=width, break_long_words=False, break_on_hyphens=False), encoding="utf-8")
        written.append((cue, str(path).replace("\\", "\\\\").replace(":", "\\:")))
    return written
