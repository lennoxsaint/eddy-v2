from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .receipts import Receipts
from .sources import Sources


TRANSCRIPT_NAMES = (
    "transcript.vtt",
    "transcript.srt",
    "transcript.md",
    "transcript.txt",
    "captions.vtt",
    "captions.srt",
    "captions.md",
)


@dataclass(frozen=True)
class TranscriptCue:
    start_s: float
    end_s: float
    text: str

    def as_dict(self) -> dict:
        return {"start_s": round(self.start_s, 3), "end_s": round(self.end_s, 3), "text": self.text}


def _parse_timestamp(value: str) -> float:
    cleaned = value.strip().replace(",", ".")
    parts = cleaned.split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    raise ValueError(f"unsupported timestamp: {value}")


def _parse_timed_transcript(text: str) -> list[TranscriptCue]:
    cues: list[TranscriptCue] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    time_pattern = re.compile(r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[\.,]\d{3})\s+-->\s+(?P<end>\d{1,2}:\d{2}(?::\d{2})?[\.,]\d{3})")
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip() and line.strip().upper() != "WEBVTT"]
        if not lines:
            continue
        match_index = next((index for index, line in enumerate(lines) if time_pattern.search(line)), None)
        if match_index is None:
            continue
        match = time_pattern.search(lines[match_index])
        if not match:
            continue
        body = " ".join(line for line in lines[match_index + 1 :] if not line.isdigit())
        body = re.sub(r"<[^>]+>", "", body).strip()
        if body:
            cues.append(TranscriptCue(_parse_timestamp(match.group("start")), _parse_timestamp(match.group("end")), body))
    return cues


def _estimate_text_duration(text: str) -> float:
    return max(4.0, min(12.0, len(text.split()) / 2.2))


def _parse_bracketed_transcript(text: str) -> list[TranscriptCue]:
    marker_pattern = re.compile(r"\[(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\]")
    markers = list(marker_pattern.finditer(text))
    cues: list[TranscriptCue] = []
    for index, marker in enumerate(markers):
        start_s = _parse_timestamp(marker.group("time"))
        next_marker = markers[index + 1] if index + 1 < len(markers) else None
        body_end = next_marker.start() if next_marker else len(text)
        body = text[marker.end() : body_end]
        body = re.sub(r"^#+\s+.*$", "", body, flags=re.MULTILINE)
        body = re.sub(r"\s+", " ", body).strip()
        if not body:
            continue
        inferred_end = _parse_timestamp(next_marker.group("time")) if next_marker else start_s + _estimate_text_duration(body)
        end_s = max(start_s + 0.75, inferred_end)
        cues.append(TranscriptCue(start_s, end_s, body))
    return cues


def _parse_plain_transcript(text: str) -> list[TranscriptCue]:
    paragraphs = [line.strip() for line in re.split(r"\n\s*\n", text) if line.strip()]
    cues: list[TranscriptCue] = []
    cursor = 0.0
    for paragraph in paragraphs[:24]:
        duration = _estimate_text_duration(paragraph)
        cues.append(TranscriptCue(cursor, cursor + duration, paragraph))
        cursor += duration
    return cues


def _candidate_transcript_dirs(folder: Path) -> list[Path]:
    dirs = [
        folder,
        folder.parent,
        folder / "edit" / "descript-export",
        folder.parent / "edit" / "descript-export",
    ]
    unique: list[Path] = []
    for path in dirs:
        if path not in unique and path.exists():
            unique.append(path)
    return unique


def _find_transcript(sources: Sources) -> Path | None:
    candidates: list[Path] = []
    for folder in _candidate_transcript_dirs(sources.folder):
        candidates.extend(list(folder.glob("*.vtt")) + list(folder.glob("*.srt")) + list(folder.glob("*.md")) + list(folder.glob("*.txt")))
    by_name = {path.name.lower(): path for path in candidates}
    for name in TRANSCRIPT_NAMES:
        if name in by_name:
            return by_name[name]
    transcript_like = [path for path in candidates if "transcript" in path.name.lower() or "caption" in path.name.lower()]
    return sorted(transcript_like)[0] if transcript_like else None


def load_transcript_cues(sources: Sources, run_dir: Path, receipts: Receipts) -> list[TranscriptCue]:
    transcript = _find_transcript(sources)
    if not transcript:
        receipts.log("transcript", status="missing", code="transcript_source_missing", folder=str(sources.folder))
        return []
    text = transcript.read_text(encoding="utf-8", errors="replace")
    if transcript.suffix.lower() in {".vtt", ".srt"}:
        cues = _parse_timed_transcript(text)
    else:
        cues = _parse_bracketed_transcript(text) or _parse_plain_transcript(text)
    payload = {"source": str(transcript), "cues": [cue.as_dict() for cue in cues]}
    (run_dir / "transcript-cues.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    receipts.log("transcript", status="pass", source=str(transcript), cue_count=len(cues), output=str(run_dir / "transcript-cues.json"))
    return cues


def semantic_chapters(cues: list[TranscriptCue], *, max_chapters: int = 8) -> list[dict]:
    chapters: list[dict] = []
    seen: set[str] = set()
    for cue in cues:
        words = cue.text.split()
        if len(words) < 3:
            continue
        title = " ".join(words[:8]).rstrip(".,:;")
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        chapters.append({"time": _format_chapter_time(cue.start_s), "title": title, "source": "transcript"})
        if len(chapters) == max_chapters:
            break
    return chapters


def _format_chapter_time(seconds: float) -> str:
    total = int(max(0, seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
