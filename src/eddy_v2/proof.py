from __future__ import annotations

import json
import shlex
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


def _cloud_budget_from_rows(rows: list[dict[str, Any]]) -> float:
    start = _latest(rows, "run_start") or {}
    try:
        return float(start.get("cloud_budget_usd", 25.0))
    except (TypeError, ValueError):
        return 25.0


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


def _format_budget(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


def _audio_profile(audio: dict[str, Any]) -> dict[str, Any]:
    profile_raw = audio.get("cloud_quality_profile")
    profile = profile_raw if isinstance(profile_raw, dict) else {}
    audio_raw = profile.get("audio")
    return audio_raw if isinstance(audio_raw, dict) else cloud_audio_profile()


def _audio_provider_attempts(audio: dict[str, Any]) -> dict[str, dict[str, Any]]:
    attempts_raw = audio.get("providers")
    attempts = attempts_raw if isinstance(attempts_raw, dict) else {}
    profile = _audio_profile(audio)
    configured_raw = profile.get("providers")
    configured = configured_raw if isinstance(configured_raw, dict) else {}
    provider_names = ("descript", "auphonic", "elevenlabs")
    result: dict[str, dict[str, Any]] = {}
    for provider in provider_names:
        attempt_raw = attempts.get(provider)
        attempt = attempt_raw if isinstance(attempt_raw, dict) else {}
        provider_profile_raw = configured.get(provider)
        provider_profile = provider_profile_raw if isinstance(provider_profile_raw, dict) else {}
        result[provider] = {
            "status": attempt.get("status") or "missing",
            "reason": attempt.get("reason"),
            "error": attempt.get("error"),
            "uploaded_media": attempt.get("uploaded_media"),
            "configured": bool(provider_profile.get("configured")),
            "missing": provider_profile.get("missing") if isinstance(provider_profile.get("missing"), list) else [],
            "unlocks": provider_profile.get("unlocks"),
        }
    return result


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _caption_proof(run_dir: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    final_dir = run_dir / "final"
    provenance_path = final_dir / "caption-provenance.json"
    provenance = read_json_object(provenance_path)
    provenance_artifact_exists = provenance is not None
    if provenance is None:
        provenance = _latest(rows, "caption_provenance")
    sidecars = [final_dir / "captions.json", final_dir / "subtitles.srt", final_dir / "subtitles.vtt"]
    sidecars_exist = all(path.exists() and path.stat().st_size > 0 for path in sidecars)
    if not provenance:
        if sidecars_exist:
            provenance = {
                "status": "warning",
                "sidecar_source": "legacy_sidecars_without_provenance",
                "speech_accurate_subtitles": False,
                "transcript_available": (run_dir / "transcript-cues.json").exists(),
                "transcript_cue_count": 0,
                "warning": "speech_accurate_subtitles_not_proven",
            }
        else:
            provenance = {
                "status": "missing",
                "sidecar_source": "missing",
                "speech_accurate_subtitles": False,
                "transcript_available": False,
                "transcript_cue_count": 0,
                "warning": "caption_sidecars_missing",
            }
    speech_accurate = bool(provenance.get("speech_accurate_subtitles"))
    status = str(provenance.get("status") or ("pass" if speech_accurate else "warning"))
    return {
        "status": status,
        "caption_sidecars_exist": sidecars_exist,
        "provenance_artifact_exists": provenance_artifact_exists,
        "provenance_artifact": str(provenance_path),
        "sidecar_source": str(provenance.get("sidecar_source") or "unknown"),
        "speech_accurate_subtitles": speech_accurate,
        "transcript_available": bool(provenance.get("transcript_available")),
        "transcript_cue_count": _int_value(provenance.get("transcript_cue_count")),
        "warning": provenance.get("warning"),
    }


def _review_reels_proof(review_packet: Any) -> dict[str, Any]:
    packet = read_json_object(Path(str(review_packet))) if review_packet else None
    reels_raw = packet.get("review_reels") if isinstance(packet, dict) else None
    reels = reels_raw if isinstance(reels_raw, dict) else {}
    long_reel = reels.get("long")
    shorts_reel = reels.get("shorts")
    review_page = packet.get("review_page") if isinstance(packet, dict) else None
    return {
        "long": str(long_reel) if long_reel else None,
        "shorts": str(shorts_reel) if shorts_reel else None,
        "review_page": str(review_page) if review_page else None,
        "long_exists": _bool_path_exists(long_reel),
        "shorts_exists": _bool_path_exists(shorts_reel),
        "review_page_exists": _bool_path_exists(review_page),
    }


def _run_provenance(run_dir: Path, scorecard: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    scorecard_provenance = scorecard.get("eddy_provenance")
    if isinstance(scorecard_provenance, dict):
        source = "scorecard"
        provenance = scorecard_provenance
    else:
        manifest = read_json_object(run_dir / "manifest.json") or {}
        manifest_provenance = manifest.get("eddy_provenance")
        if isinstance(manifest_provenance, dict):
            source = "manifest"
            provenance = manifest_provenance
        else:
            start = _latest(rows, "run_start") or {}
            start_provenance = start.get("eddy_provenance")
            source = "receipt" if isinstance(start_provenance, dict) else "missing"
            provenance = start_provenance if isinstance(start_provenance, dict) else {}

    git_raw = provenance.get("git")
    git = git_raw if isinstance(git_raw, dict) else {}
    settings_raw = provenance.get("run_settings")
    settings = settings_raw if isinstance(settings_raw, dict) else {}
    renderer_raw = provenance.get("renderer_boundary")
    renderer = renderer_raw if isinstance(renderer_raw, dict) else {}
    missing = []
    if not provenance.get("eddy_v2_version"):
        missing.append("eddy_v2_version")
    if not git.get("commit"):
        missing.append("git.commit")
    if not {"local_only", "cloud_budget_usd"}.issubset(settings):
        missing.append("run_settings")
    if not renderer.get("node_adapter"):
        missing.append("renderer_boundary")
    return {
        "status": "pass" if not missing else "missing",
        "source": source,
        "eddy_v2_version": provenance.get("eddy_v2_version"),
        "git_commit": git.get("commit"),
        "git_branch": git.get("branch"),
        "git_dirty": git.get("dirty"),
        "git_available": bool(git.get("available")),
        "run_settings": settings,
        "renderer_boundary": renderer,
        "missing": missing,
    }


def _review_command(run_dir: Path) -> str:
    quoted = shlex.quote(str(run_dir))
    return f"eddy review {quoted} --long-edit 8 --motion 8 --audio 8 --shorts 8"


def _audio_retry_command(run_dir: Path, cap: float) -> str:
    quoted = shlex.quote(str(run_dir))
    return f"eddy audio-proof {quoted} --cloud-budget {_format_budget(cap)}"


def _onepassword_audio_retry_command(run_dir: Path, cap: float, *, env_file: str = ".env.audio") -> str:
    quoted_env = shlex.quote(env_file)
    return f"op run --env-file {quoted_env} -- {_audio_retry_command(run_dir, cap)} --json"


def _unblock_actions(
    *,
    blockers: list[str],
    audio_profile: dict[str, Any],
    audio_retry_command: str,
    onepassword_audio_retry_command: str,
    review_command: str,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if "cloud_audio_credentials_missing_or_failed" in blockers:
        options_raw = audio_profile.get("audio_quality_unblock_options")
        options = options_raw if isinstance(options_raw, list) else []
        actions.append(
            {
                "blocker": "cloud_audio_credentials_missing_or_failed",
                "action": "configure_one_audio_provider",
                "options": options,
                "then_run": audio_retry_command,
                "onepassword_then_run": onepassword_audio_retry_command,
                "onepassword_env_file": ".env.audio",
            }
        )
    if "strong_studio_sound_not_proven" in blockers:
        strong_raw = audio_profile.get("strong_studio_sound_unblock")
        strong = strong_raw if isinstance(strong_raw, list) else ["DESCRIPT_API_KEY"]
        actions.append(
            {
                "blocker": "strong_studio_sound_not_proven",
                "action": "prove_descript_studio_sound_parity",
                "preferred_required": strong or ["DESCRIPT_API_KEY"],
                "then_run": audio_retry_command,
                "onepassword_then_run": onepassword_audio_retry_command,
                "onepassword_env_file": ".env.audio",
            }
        )
    if "pending_lennox_8_of_10_review" in blockers:
        actions.append(
            {
                "blocker": "pending_lennox_8_of_10_review",
                "action": "record_lennox_quality_review",
                "required_scores": {
                    "long_edit": ">=8",
                    "motion": ">=8",
                    "audio": ">=8",
                    "shorts": ">=8",
                },
                "then_run": review_command,
            }
        )
    return actions


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
    review_reels = _review_reels_proof(review_packet)
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
    if not review_reels["long_exists"]:
        hero_missing.append("review_reel:long")
    if shorts_count > 0 and not review_reels["shorts_exists"]:
        hero_missing.append("review_reel:shorts")
    if not review_reels["review_page_exists"]:
        hero_missing.append("review_page")
    if source_hash_intact is not True:
        hero_missing.append("source_hash_intact")
    failed_gates = [name for name, status in gate_statuses.items() if status != "pass"]
    if failed_gates:
        hero_missing.extend(f"gate:{name}" for name in failed_gates)

    shorts_status = "pass" if shorts_count >= 3 else "shortfall" if shorts_shortfall else "blocked"
    cloud_status = "pass" if cost_within_cap and not audio_blockers else "blocked"
    final_blockers = sorted(set(blockers + audio_blockers + human_blockers))
    final_status = "publishable" if scorecard.get("publishable_8_of_10") is True and not final_blockers else "blocked"
    audio_profile = _audio_profile(audio)
    audio_provider_attempts = _audio_provider_attempts(audio)
    audio_retry_command = _audio_retry_command(run_dir, cap or 25.0)
    onepassword_audio_retry_command = _onepassword_audio_retry_command(run_dir, cap or 25.0)
    review_command = _review_command(run_dir)
    caption = _caption_proof(run_dir, rows)
    provenance = _run_provenance(run_dir, scorecard, rows)
    unblock_actions = _unblock_actions(
        blockers=final_blockers,
        audio_profile=audio_profile,
        audio_retry_command=audio_retry_command,
        onepassword_audio_retry_command=onepassword_audio_retry_command,
        review_command=review_command,
    )

    return {
        "hero_run_proof": {
            "status": "pass" if not hero_missing else "blocked",
            "long_video_exists": long_video_exists,
            "launch_kit_exists": launch_kit.exists(),
            "review_packet_exists": _bool_path_exists(review_packet),
            "review_reels": review_reels,
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
            "audio_ready": bool(audio_profile.get("audio_ready")),
            "strong_studio_sound_ready": bool(audio_profile.get("strong_studio_sound_ready")),
            "configured_providers": audio_profile.get("configured_providers") if isinstance(audio_profile.get("configured_providers"), list) else [],
            "provider_attempts": audio_provider_attempts,
            "audio_quality_unblock_options": (
                audio_profile.get("audio_quality_unblock_options") if isinstance(audio_profile.get("audio_quality_unblock_options"), list) else []
            ),
            "audio_retry_command": audio_retry_command,
            "onepassword_audio_retry_command": onepassword_audio_retry_command,
        },
        "human_review_proof": {
            "status": human_status,
            "publishable_8_of_10": bool(scorecard.get("publishable_8_of_10")),
            "blockers": human_blockers,
            "review_command_template": review_command,
        },
        "caption_proof": caption,
        "run_provenance_proof": provenance,
        "final_publishability": {
            "status": final_status,
            "blockers": final_blockers,
            "unblock_actions": unblock_actions,
        },
    }


def proof_layers_markdown(proof_layers: dict[str, Any]) -> str:
    hero = proof_layers["hero_run_proof"]
    shorts = proof_layers["shorts_proof"]
    cloud = proof_layers["cloud_cost_proof"]
    human = proof_layers["human_review_proof"]
    caption = proof_layers.get("caption_proof", {"status": "missing"})
    provenance = proof_layers.get("run_provenance_proof", {"status": "missing"})
    final = proof_layers["final_publishability"]
    audio_retry_command = cloud.get("audio_retry_command") or "none"
    onepassword_audio_retry_command = cloud.get("onepassword_audio_retry_command") or "none"
    review_command = human.get("review_command_template") or "none"
    provider_attempts = cloud.get("provider_attempts") if isinstance(cloud.get("provider_attempts"), dict) else {}
    provider_lines = []
    for provider in ("descript", "auphonic", "elevenlabs"):
        attempt_raw = provider_attempts.get(provider) if isinstance(provider_attempts, dict) else {}
        attempt = attempt_raw if isinstance(attempt_raw, dict) else {}
        status = attempt.get("status") or "missing"
        reason = attempt.get("reason") or attempt.get("error") or "none"
        uploaded = attempt.get("uploaded_media") or "unknown"
        missing = attempt.get("missing") if isinstance(attempt.get("missing"), list) else []
        missing_text = ",".join(str(item) for item in missing) if missing else "none"
        provider_lines.append(f"- audio_provider_{provider}: {status} (reason: {reason}; uploaded_media: {uploaded}; missing: {missing_text})")
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
            f"- caption_proof: {caption.get('status', 'missing')} ({caption.get('sidecar_source', 'unknown')})",
            f"- run_provenance_proof: {provenance.get('status', 'missing')} (commit: {provenance.get('git_commit') or 'unknown'}; dirty: {provenance.get('git_dirty')})",
            f"- final_publishability: {final['status']}",
            f"- final_blockers: {', '.join(final['blockers']) if final['blockers'] else 'none'}",
            *provider_lines,
            f"- audio_retry_command: {audio_retry_command}",
            f"- onepassword_audio_retry_command: {onepassword_audio_retry_command}",
            f"- review_command: {review_command}",
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


def _receipt_final_blockers(receipts: Receipts, proof_layers: dict[str, Any]) -> None:
    final_raw = proof_layers.get("final_publishability")
    final = final_raw if isinstance(final_raw, dict) else {}
    blockers = _as_blockers(final.get("blockers"))
    previous_blockers: list[str] = []
    for row in reversed(receipts.read_all()):
        if row.get("event") == "blocker_snapshot" and row.get("scope") == "final_publishability":
            previous_blockers = _as_blockers(row.get("blockers"))
            break
    actions_raw = final.get("unblock_actions")
    actions = actions_raw if isinstance(actions_raw, list) else []
    action_by_blocker = {
        str(action.get("blocker")): action for action in actions if isinstance(action, dict) and action.get("blocker")
    }
    for blocker in sorted(set(previous_blockers) - set(blockers)):
        receipts.log(
            "blocker",
            code=blocker,
            status="resolved",
            scope="final_publishability",
        )
    receipts.log(
        "blocker_snapshot",
        scope="final_publishability",
        status=str(final.get("status") or ("blocked" if blockers else "clear")),
        blockers=blockers,
    )
    for blocker in blockers:
        action = action_by_blocker.get(blocker, {})
        receipts.log(
            "blocker",
            code=blocker,
            status="active",
            scope="final_publishability",
            unblock_action=action.get("action"),
            then_run=action.get("then_run"),
            onepassword_then_run=action.get("onepassword_then_run"),
        )


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
    if receipts:
        _receipt_final_blockers(receipts, payload["proof_layers"])
    return payload


def write_audio_proof(run_dir: Path, receipts: Receipts) -> Path:
    rows = receipts.read_all()
    proof = summarize_audio_proof(rows)
    audio_profile = _audio_profile(proof)
    provider_attempts = _audio_provider_attempts(proof)
    proof["provider_attempts"] = provider_attempts
    proof["audio_quality_unblock_options"] = (
        audio_profile.get("audio_quality_unblock_options") if isinstance(audio_profile.get("audio_quality_unblock_options"), list) else []
    )
    proof["strong_studio_sound_unblock"] = (
        audio_profile.get("strong_studio_sound_unblock") if isinstance(audio_profile.get("strong_studio_sound_unblock"), list) else []
    )
    cloud_budget = _cloud_budget_from_rows(rows)
    proof["audio_retry_command"] = _audio_retry_command(run_dir, cloud_budget)
    proof["onepassword_audio_retry_command"] = _onepassword_audio_retry_command(run_dir, cloud_budget)
    proof["allowed_upload_scope"] = {
        "descript": "audio_extract_only",
        "auphonic": "audio_extract_only",
        "elevenlabs": "audio_extract_only",
        "full_video_upload_default": False,
    }
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
        provider_attempts=provider_attempts,
        audio_retry_command=proof["audio_retry_command"],
        onepassword_audio_retry_command=proof["onepassword_audio_retry_command"],
        allowed_upload_scope=proof["allowed_upload_scope"],
    )
    return path
