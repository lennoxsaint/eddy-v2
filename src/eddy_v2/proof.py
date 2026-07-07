from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .cloud_quality import cloud_audio_profile
from .receipts import Receipts

PROVIDER_EVENTS = {
    "descript": "audio_descript_parity",
    "auphonic": "audio_auphonic_parity",
    "elevenlabs": "audio_elevenlabs_parity",
}

STRONG_BACKEND = "descript_studio_sound"
CLOUD_FALLBACK_BACKENDS = {"auphonic", "elevenlabs_audio_isolation"}
LOCAL_FALLBACK_BACKEND = "local_loudnorm_fallback"
HERO_RUN_GATES = (
    "source_safety",
    "cut_integrity",
    "motion_artifact",
    "motion_collision_proof",
    "motion_visual_qa",
    "caption_sidecars",
    "long_media_integrity",
    "launch_package",
    "final_media_probe",
)


def audio_gate_blockers(audio_summary: dict[str, Any] | None) -> list[str]:
    if not audio_summary:
        return ["audio_proof_missing"]
    if audio_summary.get("quality_status") in {"strong_studio_sound", "cloud_audio_fallback"}:
        return []
    quality_blockers = audio_summary.get("quality_blockers")
    if isinstance(quality_blockers, list) and quality_blockers:
        return [str(blocker) for blocker in quality_blockers]
    return ["audio_quality_gate_failed"]


def _latest(rows: list[dict[str, Any]], event: str) -> dict[str, Any] | None:
    for row in reversed(rows):
        if row.get("event") == event:
            return row
    return None


def summarize_audio_proof(rows: list[dict[str, Any]]) -> dict[str, Any]:
    selected = _latest(rows, "audio_polish") or {}
    selected_backend = selected.get("selected_backend")
    providers: dict[str, dict[str, Any]] = {}
    for provider, event in PROVIDER_EVENTS.items():
        row = _latest(rows, event) or {}
        providers[provider] = {
            "status": row.get("status") or "missing",
            "reason": row.get("reason"),
            "error": row.get("error"),
            "uploaded_media": row.get("uploaded_media"),
        }

    strong_studio_sound = selected_backend == STRONG_BACKEND and providers["descript"]["status"] == "pass"
    cloud_polish_proven = selected_backend in CLOUD_FALLBACK_BACKENDS
    if strong_studio_sound:
        quality_status = "strong_studio_sound"
    elif cloud_polish_proven:
        quality_status = "cloud_audio_fallback"
    elif selected_backend == LOCAL_FALLBACK_BACKEND:
        quality_status = "local_degraded_fallback"
    else:
        quality_status = "audio_polish_missing"

    quality_blockers: list[str] = []
    if not strong_studio_sound:
        quality_blockers.append("strong_studio_sound_not_proven")
    if selected_backend == LOCAL_FALLBACK_BACKEND:
        quality_blockers.append("cloud_audio_credentials_missing_or_failed")
    if not selected_backend:
        quality_blockers.append("audio_polish_receipt_missing")

    return {
        "selected_backend": selected_backend,
        "output": selected.get("output"),
        "quality_status": quality_status,
        "strong_studio_sound": strong_studio_sound,
        "cloud_polish_proven": cloud_polish_proven,
        "quality_blockers": quality_blockers,
        "cloud_quality_profile": {"audio": cloud_audio_profile()},
        "providers": providers,
    }


def read_json_object(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    parsed = json.loads(path.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, dict) else None


def _latest_gate(rows: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for row in reversed(rows):
        if row.get("event") == "gate" and row.get("name") == name:
            return row
    return None


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


def _bool_path_exists(value: Any) -> bool:
    if not value:
        return False
    try:
        return Path(str(value)).exists()
    except OSError:
        return False


def _as_blockers(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def build_proof_layers(run_dir: Path, *, scorecard: dict[str, Any] | None = None, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    scorecard = scorecard or read_json_object(run_dir / "scorecard.json") or {}
    rows = rows if rows is not None else Receipts(run_dir / "receipts.jsonl").read_all()
    cost_raw = scorecard.get("cost")
    cost = cost_raw if isinstance(cost_raw, dict) else {}
    audio_raw = scorecard.get("audio_proof")
    audio = audio_raw if isinstance(audio_raw, dict) else read_json_object(run_dir / "final" / "audio-proof.json") or {}
    blockers = _as_blockers(scorecard.get("blockers"))
    gate_statuses = {name: ((_latest_gate(rows, name) or {}).get("status") or "missing") for name in HERO_RUN_GATES}
    required_gates_pass = all(status == "pass" for status in gate_statuses.values())
    source_hash_intact = _source_hash_intact(rows)
    long_video = scorecard.get("long_video")
    long_video_exists = _bool_path_exists(long_video)
    launch_kit = run_dir / "final" / "launch-kit" / "launch-kit.json"
    review_packet = scorecard.get("review_packet")
    shorts_count = int(scorecard.get("shorts_count") or 0)
    shorts_shortfall = any(row.get("event") == "shorts_quality_shortfall" for row in rows)
    spent = float(cost.get("spent_usd") or 0.0)
    cap = float(cost.get("cap_usd") or 0.0)
    cost_within_cap = cap <= 0 or spent <= cap
    audio_blockers = audio_gate_blockers(audio)
    quality_review_raw = scorecard.get("quality_review")
    quality_review = quality_review_raw if isinstance(quality_review_raw, dict) else None
    if quality_review:
        human_status = str(quality_review.get("status") or "blocked")
        human_blockers = _as_blockers(quality_review.get("blocking_reasons"))
    else:
        human_status = "pending_lennox_8_of_10_review"
        human_blockers = ["pending_lennox_8_of_10_review"]

    hero_missing = []
    if not long_video_exists:
        hero_missing.append("long_video")
    if not launch_kit.exists():
        hero_missing.append("launch_kit")
    if not _bool_path_exists(review_packet):
        hero_missing.append("review_packet")
    if source_hash_intact is not True:
        hero_missing.append("source_hash_intact")
    failed_gates = [name for name, status in gate_statuses.items() if status != "pass"]
    if failed_gates:
        hero_missing.extend(f"gate:{name}" for name in failed_gates)

    shorts_status = "pass" if shorts_count >= 3 else "shortfall" if shorts_shortfall else "blocked"
    cloud_status = "pass" if cost_within_cap and not audio_blockers else "blocked"
    final_blockers = sorted(set(blockers + audio_blockers + human_blockers))
    final_status = "publishable" if scorecard.get("publishable_8_of_10") is True and not final_blockers else "blocked"

    return {
        "hero_run_proof": {
            "status": "pass" if not hero_missing else "blocked",
            "long_video_exists": long_video_exists,
            "launch_kit_exists": launch_kit.exists(),
            "review_packet_exists": _bool_path_exists(review_packet),
            "source_hash_intact": source_hash_intact,
            "required_gates_pass": required_gates_pass,
            "gate_statuses": gate_statuses,
            "missing_or_failed": sorted(set(hero_missing)),
        },
        "shorts_proof": {
            "status": shorts_status,
            "shorts_count": shorts_count,
            "required_shorts": 3,
            "shorts_quality_shortfall_receipted": shorts_shortfall,
        },
        "cloud_cost_proof": {
            "status": cloud_status,
            "spent_usd": spent,
            "cap_usd": cap,
            "cost_within_cap": cost_within_cap,
            "audio_quality": audio.get("quality_status") or "missing",
            "strong_studio_sound": bool(audio.get("strong_studio_sound")),
            "cloud_polish_proven": bool(audio.get("cloud_polish_proven")),
            "audio_blockers": audio_blockers,
        },
        "human_review_proof": {
            "status": human_status,
            "publishable_8_of_10": bool(scorecard.get("publishable_8_of_10")),
            "blockers": human_blockers,
        },
        "final_publishability": {
            "status": final_status,
            "blockers": final_blockers,
        },
    }


def proof_layers_markdown(proof_layers: dict[str, Any]) -> str:
    hero = proof_layers["hero_run_proof"]
    shorts = proof_layers["shorts_proof"]
    cloud = proof_layers["cloud_cost_proof"]
    human = proof_layers["human_review_proof"]
    final = proof_layers["final_publishability"]
    return "\n".join(
        [
            "<!-- proof-layers:start -->",
            "## Proof Layers",
            "",
            f"- hero_run_proof: {hero['status']}",
            f"- shorts_proof: {shorts['status']} ({shorts['shorts_count']}/{shorts['required_shorts']})",
            f"- cloud_cost_proof: {cloud['status']} (${cloud['spent_usd']:.4f} / ${cloud['cap_usd']:.2f})",
            f"- audio_quality: {cloud['audio_quality']}",
            f"- human_review_proof: {human['status']}",
            f"- final_publishability: {final['status']}",
            f"- final_blockers: {', '.join(final['blockers']) if final['blockers'] else 'none'}",
            "<!-- proof-layers:end -->",
        ]
    )


def upsert_scorecard_proof_markdown(path: Path, proof_layers: dict[str, Any]) -> None:
    if not path.exists():
        return
    section = proof_layers_markdown(proof_layers).splitlines()
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index("<!-- proof-layers:start -->") if "<!-- proof-layers:start -->" in lines else -1
    end = lines.index("<!-- proof-layers:end -->") if "<!-- proof-layers:end -->" in lines else -1
    if start >= 0 and end >= start:
        lines = lines[:start] + section + lines[end + 1 :]
    else:
        lines = lines + [""] + section
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def refresh_scorecard_proof_layers(
    run_dir: Path,
    *,
    blockers: list[str] | None = None,
    cost_summary: dict[str, float] | None = None,
    receipts: Receipts | None = None,
) -> dict[str, Any] | None:
    scorecard_path = run_dir / "scorecard.json"
    payload = read_json_object(scorecard_path)
    if not payload:
        return None
    if blockers is not None:
        payload["blockers"] = list(dict.fromkeys(str(blocker) for blocker in blockers))
        payload["status"] = "blocked" if payload["blockers"] else "complete"
    if cost_summary is not None:
        payload["cost"] = cost_summary
    rows = receipts.read_all() if receipts else None
    payload["proof_layers"] = build_proof_layers(run_dir, scorecard=payload, rows=rows)
    scorecard_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    upsert_scorecard_proof_markdown(run_dir / "scorecard.md", payload["proof_layers"])
    return payload


def write_audio_proof(run_dir: Path, receipts: Receipts) -> Path:
    proof = summarize_audio_proof(receipts.read_all())
    path = run_dir / "final" / "audio-proof.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(proof, indent=2), encoding="utf-8")
    receipts.log(
        "audio_proof",
        status="pass",
        proof=str(path),
        selected_backend=proof["selected_backend"],
        quality_status=proof["quality_status"],
        strong_studio_sound=proof["strong_studio_sound"],
        quality_blockers=proof["quality_blockers"],
        cloud_quality_profile=proof["cloud_quality_profile"],
    )
    return path
