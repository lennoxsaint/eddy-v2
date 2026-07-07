from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .proof import read_json_object, refresh_scorecard_proof_layers
from .receipts import Receipts

CRITERIA = {
    "long_edit_story": "long edit story",
    "motion_graphics": "motion graphics",
    "audio_polish": "audio polish",
    "shorts_watchability": "Shorts watchability",
}
REQUIRED_SCORE = 8.0


def _read_json(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"expected JSON object: {path}")
    return parsed


def _blocking_reasons(scorecard: dict[str, Any], audio_proof: dict[str, Any] | None, scores: dict[str, float]) -> list[str]:
    reasons: list[str] = []
    blockers = scorecard.get("blockers")
    if isinstance(blockers, list) and blockers:
        reasons.extend(str(blocker) for blocker in blockers)
    for name, score in scores.items():
        if score < REQUIRED_SCORE:
            reasons.append(f"{name}_below_8")
    audio_blockers = (audio_proof or {}).get("quality_blockers")
    if isinstance(audio_blockers, list):
        reasons.extend(str(blocker) for blocker in audio_blockers)
    elif audio_proof is None:
        reasons.append("audio_proof_missing")
    return sorted(set(reasons))


def _criteria_rows(scores: dict[str, float]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, label in CRITERIA.items():
        score = float(scores[name])
        rows.append(
            {
                "name": name,
                "label": label,
                "required_score": REQUIRED_SCORE,
                "score": score,
                "status": "pass" if score >= REQUIRED_SCORE else "failed",
            }
        )
    return rows


def _update_scorecard_md(path: Path, review: dict[str, Any]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else ["# Eddy V2 Scorecard", ""]
    replacements = {
        "- publishable_8_of_10:": f"- publishable_8_of_10: {str(review['publishable_8_of_10']).lower()}",
        "- review_status:": f"- review_status: {review['status']}",
        "- review_blockers:": f"- review_blockers: {', '.join(review['blocking_reasons']) if review['blocking_reasons'] else 'none'}",
    }
    for prefix, replacement in replacements.items():
        if any(line.startswith(prefix) for line in lines):
            lines = [replacement if line.startswith(prefix) else line for line in lines]
        else:
            lines.append(replacement)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def apply_quality_review(
    run_dir: Path,
    scores: dict[str, float],
    *,
    reviewer: str = "Lennox",
    notes: str = "",
) -> dict[str, Any]:
    missing = sorted(set(CRITERIA) - set(scores))
    if missing:
        raise ValueError(f"missing review scores: {','.join(missing)}")
    clean_scores = {name: float(scores[name]) for name in CRITERIA}
    scorecard_path = run_dir / "scorecard.json"
    review_packet_path = run_dir / "final" / "review" / "review-packet.json"
    if not scorecard_path.exists():
        raise FileNotFoundError(f"scorecard not found: {scorecard_path}")
    if not review_packet_path.exists():
        raise FileNotFoundError(f"review packet not found: {review_packet_path}")

    scorecard = _read_json(scorecard_path)
    packet = _read_json(review_packet_path)
    audio_proof_path = run_dir / "final" / "audio-proof.json"
    audio_proof = read_json_object(audio_proof_path)
    blocking_reasons = _blocking_reasons(scorecard, audio_proof, clean_scores)
    publishable = not blocking_reasons
    review = {
        "status": "pass" if publishable else "blocked",
        "reviewer": reviewer,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "required_score": REQUIRED_SCORE,
        "scores": clean_scores,
        "criteria": _criteria_rows(clean_scores),
        "blocking_reasons": blocking_reasons,
        "publishable_8_of_10": publishable,
        "notes": notes,
    }

    packet["status"] = "reviewed_publishable" if publishable else "reviewed_blocked"
    packet["publishable_8_of_10"] = publishable
    packet["criteria"] = review["criteria"]
    packet["quality_review"] = review
    review_packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")

    scorecard["publishable_8_of_10"] = publishable
    scorecard["quality_review"] = review
    scorecard_path.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")
    _update_scorecard_md(run_dir / "scorecard.md", review)
    refresh_scorecard_proof_layers(run_dir)

    Receipts(run_dir / "receipts.jsonl").log(
        "quality_review",
        status=review["status"],
        reviewer=reviewer,
        scores=clean_scores,
        publishable_8_of_10=publishable,
        blocking_reasons=blocking_reasons,
    )
    return review
