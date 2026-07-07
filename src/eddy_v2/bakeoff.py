from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .commands import ffprobe_json
from .proof import read_json_object
from .receipts import Receipts


CURRENT_EDDY_RUNS = Path("/Users/lennoxsaint/eddy/runs")


@dataclass(frozen=True)
class MediaSummary:
    path: str | None
    exists: bool
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "exists": self.exists,
            "duration_s": self.duration_s,
            "width": self.width,
            "height": self.height,
            "error": self.error,
        }


def _json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _receipt_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _media_summary(path: Path | None) -> MediaSummary:
    if path is None:
        return MediaSummary(path=None, exists=False)
    if not path.exists():
        return MediaSummary(path=str(path), exists=False)
    try:
        probe = ffprobe_json(path)
        streams_raw = probe.get("streams")
        streams: list[Any] = streams_raw if isinstance(streams_raw, list) else []
        video: dict[str, Any] = next((stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"), {})
        format_raw = probe.get("format")
        format_data: dict[str, Any] = format_raw if isinstance(format_raw, dict) else {}
        duration = format_data.get("duration")
        return MediaSummary(
            path=str(path),
            exists=True,
            duration_s=round(float(duration), 3) if duration is not None else None,
            width=video.get("width") if isinstance(video.get("width"), int) else None,
            height=video.get("height") if isinstance(video.get("height"), int) else None,
        )
    except Exception as exc:
        return MediaSummary(path=str(path), exists=True, error=str(exc))


def _find_long_video(run_dir: Path) -> Path | None:
    preferred = [
        run_dir / "final" / "video.mp4",
        run_dir / "video.mp4",
        run_dir / "final.mp4",
        run_dir / "output.mp4",
    ]
    for path in preferred:
        if path.exists():
            return path
    candidates = [path for path in run_dir.rglob("*.mp4") if "video_segments" not in path.parts and "quarantine" not in path.parts]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_size)


def _shorts(run_dir: Path) -> list[str]:
    shorts_dir = run_dir / "final" / "shorts"
    if shorts_dir.exists():
        return [str(path) for path in sorted(shorts_dir.glob("short-*.mp4")) if path.is_file()]
    candidates = [path for path in run_dir.rglob("*.mp4") if "short" in path.name.lower() and "quarantine" not in path.parts]
    return [str(path) for path in sorted(candidates)]


def _source_hash_intact(rows: list[dict[str, Any]]) -> bool | None:
    by_label: dict[str, dict[str, str]] = {}
    for row in rows:
        if row.get("event") != "source_hash":
            continue
        label = str(row.get("label") or "")
        phase = str(row.get("phase") or "")
        sha = str(row.get("sha256") or "")
        if label and phase in {"before", "after"} and sha:
            by_label.setdefault(label, {})[phase] = sha
    if not by_label:
        return None
    return all(value.get("before") == value.get("after") for value in by_label.values())


def summarize_run(run_dir: Path, *, label: str) -> dict[str, Any]:
    scorecard = _json(run_dir / "scorecard.json")
    rows = _receipt_rows(run_dir / "receipts.jsonl")
    long_video = _find_long_video(run_dir)
    shorts = _shorts(run_dir)
    cost_raw = scorecard.get("cost")
    cost: dict[str, Any] = cost_raw if isinstance(cost_raw, dict) else {}
    audio_proof = read_json_object(run_dir / "final" / "audio-proof.json")
    blockers_raw = scorecard.get("blockers")
    blockers = blockers_raw if isinstance(blockers_raw, list) else []
    return {
        "label": label,
        "run_dir": str(run_dir),
        "status": scorecard.get("status") or ("present" if run_dir.exists() else "missing"),
        "long_video": _media_summary(long_video).as_dict(),
        "shorts_count": len(shorts),
        "shorts": shorts,
        "receipts": {
            "path": str(run_dir / "receipts.jsonl"),
            "exists": (run_dir / "receipts.jsonl").exists(),
            "row_count": len(rows),
        },
        "cost": {
            "spent_usd": cost.get("spent_usd"),
            "cap_usd": cost.get("cap_usd"),
        },
        "audio_proof": audio_proof,
        "source_hash_intact": _source_hash_intact(rows),
        "blockers": blockers,
    }


def _receipt_head_matches(receipts: Path, folder: Path) -> bool:
    try:
        with receipts.open("r", encoding="utf-8", errors="replace") as handle:
            head = handle.read(262_144)
    except OSError:
        return False
    needle = str(folder.resolve())
    camera = str((folder / "camera.mp4").resolve())
    screen = str((folder / "screen.mp4").resolve())
    return needle in head or camera in head or screen in head


def discover_current_eddy_run(folder: Path, *, search_root: Path = CURRENT_EDDY_RUNS) -> Path | None:
    if not search_root.exists():
        return None
    candidates: list[Path] = []
    for receipts in search_root.glob("*/receipts.jsonl"):
        run_dir = receipts.parent
        if _find_long_video(run_dir) and _receipt_head_matches(receipts, folder):
            candidates.append(run_dir)
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def build_bakeoff_report(
    *,
    folder: Path,
    v2_run_dir: Path,
    current_run_dir: Path | None = None,
    receipts: Receipts | None = None,
) -> dict[str, Any]:
    discovered_current = current_run_dir or discover_current_eddy_run(folder)
    current_output_proof: dict[str, Any]
    if discovered_current:
        current_output_proof = {"status": "compared", "run_dir": str(discovered_current)}
    else:
        current_output_proof = {
            "label": "current-eddy",
            "status": "missing",
            "reason": "current_output_proof_missing",
            "searched": str(CURRENT_EDDY_RUNS),
        }
    if receipts:
        receipts.log(
            "bakeoff_compare",
            status=current_output_proof["status"],
            report=str(v2_run_dir / "bakeoff.json"),
            current_run=current_output_proof.get("run_dir"),
            reason=current_output_proof.get("reason"),
        )

    v2 = summarize_run(v2_run_dir, label="eddy-v2")
    current: dict[str, Any]
    if discovered_current:
        current = summarize_run(discovered_current, label="current-eddy")
    else:
        current = current_output_proof

    comparison = _comparison(v2, current)
    report = {
        "hero_folder": str(folder.resolve()),
        "winner": "undecided_pending_lennox_8_of_10_review",
        "winner_bar": "Lennox would publish it; long edit, motion, audio, and Shorts are each 8/10+.",
        "current_output_proof": current_output_proof,
        "candidates": {"eddy_v2": v2, "current_eddy": current},
        "comparison": comparison,
    }
    (v2_run_dir / "bakeoff.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (v2_run_dir / "bakeoff.md").write_text(_markdown(report), encoding="utf-8")
    return report


def _comparison(v2: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    if current.get("status") == "missing":
        return {
            "status": "current_output_proof_missing",
            "notes": ["Current Eddy final media proof was not found, so quality comparison remains pending."],
        }
    v2_long = v2["long_video"]
    current_long = current["long_video"]
    return {
        "status": "metrics_compared",
        "long_duration_delta_s": _delta(v2_long.get("duration_s"), current_long.get("duration_s")),
        "shorts_count_delta": int(v2.get("shorts_count") or 0) - int(current.get("shorts_count") or 0),
        "v2_source_hash_intact": v2.get("source_hash_intact"),
        "current_source_hash_intact": current.get("source_hash_intact"),
        "v2_audio_quality": (v2.get("audio_proof") or {}).get("quality_status"),
        "current_audio_quality": (current.get("audio_proof") or {}).get("quality_status"),
        "human_quality_review": "pending_lennox_8_of_10_review",
    }


def _delta(left: float | int | None, right: float | int | None) -> float | None:
    if left is None or right is None:
        return None
    return round(float(left) - float(right), 3)


def _markdown(report: dict[str, Any]) -> str:
    v2 = report["candidates"]["eddy_v2"]
    current = report["candidates"]["current_eddy"]
    comparison = report["comparison"]
    lines = [
        "# Eddy V2 Bakeoff",
        "",
        f"- hero_folder: {report['hero_folder']}",
        f"- winner: {report['winner']}",
        f"- winner_bar: {report['winner_bar']}",
        f"- current_output_proof: {report['current_output_proof']['status']}",
        "",
        "## Eddy V2",
        "",
        f"- run_dir: {v2['run_dir']}",
        f"- status: {v2['status']}",
        f"- long_video: {v2['long_video']['path']}",
        f"- long_duration_s: {v2['long_video']['duration_s']}",
        f"- shorts_count: {v2['shorts_count']}",
        f"- audio_quality: {(v2.get('audio_proof') or {}).get('quality_status', 'missing')}",
        f"- receipts_rows: {v2['receipts']['row_count']}",
        f"- source_hash_intact: {v2['source_hash_intact']}",
        "",
        "## Current Eddy",
        "",
    ]
    if current.get("status") == "missing":
        lines.extend(
            [
                "- status: missing",
                f"- reason: {current['reason']}",
                f"- searched: {current['searched']}",
            ]
        )
    else:
        lines.extend(
            [
                f"- run_dir: {current['run_dir']}",
                f"- status: {current['status']}",
                f"- long_video: {current['long_video']['path']}",
                f"- long_duration_s: {current['long_video']['duration_s']}",
                f"- shorts_count: {current['shorts_count']}",
                f"- audio_quality: {(current.get('audio_proof') or {}).get('quality_status', 'missing')}",
                f"- receipts_rows: {current['receipts']['row_count']}",
                f"- source_hash_intact: {current['source_hash_intact']}",
            ]
        )
    lines.extend(["", "## Comparison", "", f"- status: {comparison['status']}"])
    if comparison.get("long_duration_delta_s") is not None:
        lines.append(f"- long_duration_delta_s: {comparison['long_duration_delta_s']}")
    if comparison.get("shorts_count_delta") is not None:
        lines.append(f"- shorts_count_delta: {comparison['shorts_count_delta']}")
    if comparison.get("notes"):
        lines.extend(f"- note: {note}" for note in comparison["notes"])
    lines.append("- human_quality_review: pending_lennox_8_of_10_review")
    lines.append("")
    return "\n".join(lines)
