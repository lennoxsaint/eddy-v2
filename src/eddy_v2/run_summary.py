from __future__ import annotations

from pathlib import Path
from typing import Any

from .proof import read_json_object
from .receipts import Receipts


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _review_page(scorecard: dict[str, Any]) -> str | None:
    packet_path = scorecard.get("review_packet")
    packet = read_json_object(Path(str(packet_path))) if packet_path else None
    page = (packet or {}).get("review_page")
    return str(page) if page else None


def _proof_statuses(proof_layers: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in (
        "hero_run_proof",
        "shorts_proof",
        "cloud_cost_proof",
        "human_review_proof",
        "caption_proof",
        "run_provenance_proof",
        "final_publishability",
    ):
        layer = _dict(proof_layers.get(name))
        result[name] = str(layer.get("status") or "missing")
    return result


def build_run_output_payload(
    run_dir: Path,
    *,
    status: str | None = None,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    scorecard_path = run_dir / "scorecard.json"
    receipts_path = run_dir / "receipts.jsonl"
    scorecard = read_json_object(scorecard_path) or {}
    proof_layers = _dict(scorecard.get("proof_layers"))
    final_publishability = _dict(proof_layers.get("final_publishability"))
    human_review = _dict(proof_layers.get("human_review_proof"))
    cloud_cost = _dict(proof_layers.get("cloud_cost_proof"))
    run_provenance = _dict(proof_layers.get("run_provenance_proof"))
    scorecard_blockers = _list(scorecard.get("blockers"))
    final_blockers = _list(final_publishability.get("blockers"))
    selected_blockers = [str(item) for item in final_blockers or blockers or scorecard_blockers]
    rows = Receipts(receipts_path).read_all() if receipts_path.exists() else []
    return {
        "run_dir": str(run_dir),
        "status": status or str(scorecard.get("status") or "unknown"),
        "blockers": selected_blockers,
        "scorecard": str(scorecard_path) if scorecard_path.exists() else None,
        "scorecard_md": str(run_dir / "scorecard.md") if (run_dir / "scorecard.md").exists() else None,
        "receipts": {
            "path": str(receipts_path),
            "exists": receipts_path.exists(),
            "row_count": len(rows),
        },
        "long_video": scorecard.get("long_video"),
        "shorts_count": int(scorecard.get("shorts_count") or 0),
        "shorts": [str(path) for path in _list(scorecard.get("shorts"))],
        "cost": scorecard.get("cost") or {},
        "eddy_provenance": scorecard.get("eddy_provenance") or {},
        "proof_statuses": _proof_statuses(proof_layers),
        "run_provenance": run_provenance,
        "review_page": _review_page(scorecard),
        "review_command": human_review.get("review_command_template"),
        "audio_retry_command": cloud_cost.get("audio_retry_command"),
        "next_actions": _list(final_publishability.get("unblock_actions")),
    }
