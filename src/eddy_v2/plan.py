from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .commands import duration_s, run_command
from .models import EditIntent
from .receipts import Receipts
from .sources import Sources
from .transcript import TranscriptCue, load_transcript_cues, semantic_chapters


@dataclass(frozen=True)
class Segment:
    start_s: float
    duration_s: float
    reason: str

    def as_dict(self) -> dict:
        return {"start_s": round(self.start_s, 3), "duration_s": round(self.duration_s, 3), "reason": self.reason}


@dataclass(frozen=True)
class EditPlan:
    source_duration_s: float
    long_segment: Segment
    short_starts_s: list[float]
    non_silent_intervals: list[tuple[float, float]]
    transcript_cue_count: int = 0
    semantic_chapters: list[dict] | None = None

    def as_dict(self) -> dict:
        return {
            "source_duration_s": round(self.source_duration_s, 3),
            "long_segment": self.long_segment.as_dict(),
            "short_starts_s": [round(start, 3) for start in self.short_starts_s],
            "non_silent_intervals": [[round(start, 3), round(end, 3)] for start, end in self.non_silent_intervals],
            "transcript_cue_count": self.transcript_cue_count,
            "semantic_chapters": self.semantic_chapters or [],
        }


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
    for gap in (distribution_gap, short_duration_s, short_duration_s / 2, 0.0):
        starts: list[float] = []
        for _, start in scored:
            if all(abs(start - existing) >= gap for existing in starts):
                starts.append(start)
            if len(starts) == target_count:
                return [round(value, 3) for value in sorted(starts)]
    return []


def select_semantic_short_starts(
    cues: list[TranscriptCue],
    source_duration: float,
    target_count: int,
    *,
    short_duration_s: float = 15.0,
) -> list[float]:
    if target_count <= 0 or source_duration < short_duration_s:
        return []
    max_start = source_duration - short_duration_s
    scored: list[tuple[float, float]] = []
    for cue in cues:
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
    transcript_cues = load_transcript_cues(sources, run_dir, receipts)
    chapters = semantic_chapters(transcript_cues)
    if chapters:
        receipts.log("semantic_plan", status="pass", source="transcript", chapter_count=len(chapters))
    else:
        receipts.log("semantic_plan", status="fallback", reason="transcript_cues_unavailable")
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
    long_segment = select_long_segment(intervals, source_duration, intent.target_duration_s)
    short_starts = select_semantic_short_starts(transcript_cues, source_duration, intent.shorts_target)
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
    )
    (run_dir / "edit-plan.json").write_text(json.dumps(plan.as_dict(), indent=2), encoding="utf-8")
    receipts.log(
        "cut_plan",
        status="pass",
        long_segment=long_segment.as_dict(),
        short_starts_s=short_starts,
        non_silent_interval_count=len(intervals),
        transcript_cue_count=len(transcript_cues),
        semantic_chapter_count=len(chapters),
        short_start_source=short_start_source,
    )
    return plan
