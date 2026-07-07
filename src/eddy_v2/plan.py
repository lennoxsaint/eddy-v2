from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .commands import duration_s, run_command
from .models import EditIntent
from .receipts import Receipts
from .sources import Sources
from .transcript import TranscriptCue, format_chapter_time, load_transcript_cues


@dataclass(frozen=True)
class Segment:
    start_s: float
    duration_s: float
    reason: str

    def as_dict(self) -> dict:
        return {"start_s": round(self.start_s, 3), "duration_s": round(self.duration_s, 3), "reason": self.reason}

    @property
    def end_s(self) -> float:
        return self.start_s + self.duration_s


@dataclass(frozen=True)
class EditPlan:
    source_duration_s: float
    long_segment: Segment
    short_starts_s: list[float]
    non_silent_intervals: list[tuple[float, float]]
    transcript_cue_count: int = 0
    semantic_chapters: list[dict] | None = None
    long_segments: tuple[Segment, ...] | None = None

    def as_dict(self) -> dict:
        return {
            "source_duration_s": round(self.source_duration_s, 3),
            "long_segment": self.long_segment.as_dict(),
            "long_segments": [segment.as_dict() for segment in self.source_segments()],
            "long_duration_s": round(self.long_duration_s, 3),
            "short_starts_s": [round(start, 3) for start in self.short_starts_s],
            "non_silent_intervals": [[round(start, 3), round(end, 3)] for start, end in self.non_silent_intervals],
            "transcript_cue_count": self.transcript_cue_count,
            "semantic_chapters": self.semantic_chapters or [],
        }

    @property
    def long_duration_s(self) -> float:
        return sum(segment.duration_s for segment in self.source_segments())

    def source_segments(self) -> tuple[Segment, ...]:
        return self.long_segments or (self.long_segment,)


def parse_silence(stderr: str, source_duration: float) -> list[tuple[float, float]]:
    starts = [float(match.group(1)) for match in re.finditer(r"silence_start: ([0-9.]+)", stderr)]
    ends = [float(match.group(1)) for match in re.finditer(r"silence_end: ([0-9.]+)", stderr)]
    silences: list[tuple[float, float]] = []
    for index, start in enumerate(starts):
        end = ends[index] if index < len(ends) else source_duration
        if end > start:
            silences.append((max(0.0, start), min(source_duration, end)))
    intervals: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in silences:
        if start > cursor:
            intervals.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < source_duration:
        intervals.append((cursor, source_duration))
    return merge_intervals([(start, end) for start, end in intervals if end - start >= 0.75])


def merge_intervals(intervals: list[tuple[float, float]], *, max_gap_s: float = 0.35) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if not merged or start - merged[-1][1] > max_gap_s:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def select_long_segment(intervals: list[tuple[float, float]], source_duration: float, target_duration: float) -> Segment:
    duration = max(1.0, min(target_duration, source_duration))
    for start, end in intervals:
        if end - start >= 3.0:
            return Segment(start_s=start, duration_s=min(duration, source_duration - start), reason="first_non_silent_audio")
    return Segment(start_s=0.0, duration_s=duration, reason="fallback_start_of_source")


def _candidate_edit_decision_paths(folder: Path) -> list[Path]:
    candidates = [
        folder / "edit-decisions.json",
        folder.parent / "edit-decisions.json",
        folder / "edit" / "edit-decisions.json",
        folder.parent / "edit" / "edit-decisions.json",
    ]
    return [path for path in candidates if path.exists()]


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _segments_from_edit_decisions(
    sources: Sources,
    source_duration: float,
    target_duration: float,
    receipts: Receipts,
) -> tuple[Segment, ...]:
    for path in _candidate_edit_decision_paths(sources.folder):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            receipts.log("edit_decision_sidecar", status="invalid", source=str(path), error=str(exc))
            continue
        raw_segments = payload.get("segments")
        if not isinstance(raw_segments, list):
            receipts.log("edit_decision_sidecar", status="invalid", source=str(path), error="segments_not_list")
            continue
        selected: list[Segment] = []
        remaining = max(1.0, min(target_duration, source_duration))
        for index, item in enumerate(raw_segments):
            if not isinstance(item, dict):
                continue
            start = _number(item.get("start"))
            end = _number(item.get("end"))
            if start is None or end is None:
                continue
            start = max(0.0, start)
            end = min(source_duration, end)
            if end - start < 0.75:
                continue
            duration = min(end - start, remaining)
            selected.append(
                Segment(
                    start_s=start,
                    duration_s=duration,
                    reason=f"edit_decision:{item.get('id') or index + 1}",
                )
            )
            remaining -= duration
            if remaining <= 0.01:
                break
        if selected:
            total = sum(segment.duration_s for segment in selected)
            receipts.log(
                "edit_decision_sidecar",
                status="pass",
                source=str(path),
                segment_count=len(selected),
                selected_duration_s=round(total, 3),
            )
            return tuple(selected)
        receipts.log("edit_decision_sidecar", status="invalid", source=str(path), error="no_valid_segments")
    return ()


def _cue_in_segments(cue: TranscriptCue, segments: tuple[Segment, ...]) -> bool:
    return any(cue.start_s < segment.end_s and cue.end_s > segment.start_s for segment in segments)


def _source_time_to_timeline(source_s: float, segments: tuple[Segment, ...]) -> float | None:
    cursor = 0.0
    for segment in segments:
        if segment.start_s <= source_s <= segment.end_s:
            return cursor + (source_s - segment.start_s)
        cursor += segment.duration_s
    return None


def semantic_chapters_for_segments(cues: list[TranscriptCue], segments: tuple[Segment, ...], *, max_chapters: int = 8) -> list[dict]:
    chapters: list[dict] = []
    seen: set[str] = set()
    for cue in cues:
        timeline_s = _source_time_to_timeline(cue.start_s, segments)
        if timeline_s is None:
            continue
        words = cue.text.split()
        if len(words) < 3:
            continue
        title = " ".join(words[:8]).rstrip(".,:;")
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        chapters.append(
            {
                "time": format_chapter_time(timeline_s),
                "title": title,
                "source": "transcript",
                "source_s": round(cue.start_s, 3),
                "timeline_s": round(timeline_s, 3),
            }
        )
        if len(chapters) == max_chapters:
            break
    return chapters


def select_short_starts(intervals: list[tuple[float, float]], source_duration: float, target_count: int, *, short_duration_s: float = 15.0) -> list[float]:
    if target_count <= 0 or source_duration < short_duration_s:
        return []
    max_start = source_duration - short_duration_s
    anchors = [0.10, 0.38, 0.66, 0.84, 0.24, 0.52]
    candidate_starts: set[float] = {max(0.0, min(max_start, source_duration * anchor)) for anchor in anchors}
    for start, end in intervals:
        midpoint = start + ((end - start) / 2)
        candidate_starts.add(max(0.0, min(max_start, start - 1.5)))
        candidate_starts.add(max(0.0, min(max_start, midpoint - (short_duration_s / 2))))
        candidate_starts.add(max(0.0, min(max_start, end - short_duration_s + 1.5)))

    scored: list[tuple[float, float]] = []
    for start in candidate_starts:
        end = start + short_duration_s
        speech_s = sum(max(0.0, min(end, interval_end) - max(start, interval_start)) for interval_start, interval_end in intervals)
        burst_count = sum(1 for interval_start, interval_end in intervals if min(end, interval_end) > max(start, interval_start))
        score = speech_s + (burst_count * 0.15)
        if score > 0:
            scored.append((score, start))
    if not scored:
        scored = [(1.0, max(0.0, min(max_start, source_duration * anchor))) for anchor in anchors]
    scored.sort(key=lambda item: (-item[0], item[1]))

    distribution_gap = min(max(short_duration_s, source_duration / max(target_count * 6, 1)), short_duration_s * 24)
    best: list[float] = []
    for gap in (distribution_gap, short_duration_s):
        starts: list[float] = []
        for _, start in scored:
            if all(abs(start - existing) >= gap for existing in starts):
                starts.append(start)
            if len(starts) == target_count:
                return [round(value, 3) for value in sorted(starts)]
        if len(starts) > len(best):
            best = starts
    return [round(value, 3) for value in sorted(best)]


def select_semantic_short_starts(
    cues: list[TranscriptCue],
    source_duration: float,
    target_count: int,
    *,
    short_duration_s: float = 15.0,
    allowed_segments: tuple[Segment, ...] | None = None,
) -> list[float]:
    if target_count <= 0 or source_duration < short_duration_s:
        return []
    max_start = source_duration - short_duration_s
    scored: list[tuple[float, float]] = []
    for cue in cues:
        if allowed_segments and not _cue_in_segments(cue, allowed_segments):
            continue
        words = cue.text.split()
        if len(words) < 4:
            continue
        start = max(0.0, min(max_start, cue.start_s - 1.0))
        score = min(len(words), 24) + min(max(cue.end_s - cue.start_s, 0.0), short_duration_s)
        scored.append((score, start))
    scored.sort(key=lambda item: (-item[0], item[1]))
    starts: list[float] = []
    for _, start in scored:
        if all(abs(start - existing) >= short_duration_s for existing in starts):
            starts.append(start)
        if len(starts) == target_count:
            return [round(value, 3) for value in sorted(starts)]
    return [round(value, 3) for value in sorted(starts)]


def create_edit_plan(sources: Sources, run_dir: Path, intent: EditIntent, receipts: Receipts) -> EditPlan:
    run_dir.mkdir(parents=True, exist_ok=True)
    source_duration = duration_s(sources.camera)
    proc = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(sources.mic or sources.camera),
            "-af",
            "silencedetect=noise=-35dB:d=0.45",
            "-f",
            "null",
            "-",
        ],
        receipts,
        event="ffmpeg",
        timeout_s=1800,
        check=False,
    )
    intervals = parse_silence(proc.stderr, source_duration)
    if not intervals:
        intervals = [(0.0, source_duration)]
    long_segments = _segments_from_edit_decisions(sources, source_duration, intent.target_duration_s, receipts)
    long_segment = long_segments[0] if long_segments else select_long_segment(intervals, source_duration, intent.target_duration_s)
    if not long_segments:
        long_segments = (long_segment,)
    preferred_segments = [(segment.start_s, segment.end_s) for segment in long_segments]
    transcript_cues = load_transcript_cues(sources, run_dir, receipts, preferred_segments=preferred_segments)
    chapters = semantic_chapters_for_segments(transcript_cues, long_segments)
    if chapters:
        receipts.log(
            "semantic_plan",
            status="pass",
            source="transcript",
            chapter_count=len(chapters),
            timeline="edited_long",
        )
    else:
        receipts.log("semantic_plan", status="fallback", reason="transcript_cues_unavailable_or_outside_long_segments")
    short_starts = select_semantic_short_starts(
        transcript_cues,
        source_duration,
        intent.shorts_target,
        allowed_segments=long_segments if any(segment.reason.startswith("edit_decision:") for segment in long_segments) else None,
    )
    short_start_source = "transcript" if short_starts else "audio_density"
    if not short_starts:
        short_starts = select_short_starts(intervals, source_duration, intent.shorts_target)
    plan = EditPlan(
        source_duration_s=source_duration,
        long_segment=long_segment,
        short_starts_s=short_starts,
        non_silent_intervals=intervals[:250],
        transcript_cue_count=len(transcript_cues),
        semantic_chapters=chapters,
        long_segments=long_segments,
    )
    (run_dir / "edit-plan.json").write_text(json.dumps(plan.as_dict(), indent=2), encoding="utf-8")
    receipts.log(
        "cut_plan",
        status="pass",
        long_segment=long_segment.as_dict(),
        long_segments=[segment.as_dict() for segment in long_segments],
        long_duration_s=round(sum(segment.duration_s for segment in long_segments), 3),
        short_starts_s=short_starts,
        non_silent_interval_count=len(intervals),
        transcript_cue_count=len(transcript_cues),
        semantic_chapter_count=len(chapters),
        short_start_source=short_start_source,
    )
    return plan
