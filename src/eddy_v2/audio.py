from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .commands import duration_s, run_command
from .cost import CostTracker
from .policy import RunPolicy
from .receipts import Receipts
from .sources import Sources


DESCRIPT_API_BASE = "https://descriptapi.com/v1"
DESCRIPT_MEDIA_NAME = "source-audio.wav"


def _descript_api_base() -> str:
    return os.environ.get("EDDY_V2_DESCRIPT_API_BASE", DESCRIPT_API_BASE).rstrip("/")


def _dict_payload(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _redacted_job(job: dict[str, Any]) -> dict[str, Any]:
    result = _dict_payload(job.get("result"))
    return {
        "job_id": job.get("job_id"),
        "job_type": job.get("job_type"),
        "job_state": job.get("job_state"),
        "project_id": job.get("project_id"),
        "project_url": job.get("project_url"),
        "result_status": result.get("status"),
        "media_seconds_used": result.get("media_seconds_used"),
        "ai_credits_used": result.get("ai_credits_used"),
        "resolved_model": result.get("resolved_model"),
    }


def _descript_json_request(method: str, path: str, token: str, payload: dict[str, Any] | None, receipts: Receipts) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    url = f"{_descript_api_base()}{path}"
    receipts.log("descript_api", phase="start", method=method, path=path)
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        receipts.log("descript_api", phase="finish", method=method, path=path, status_code=getattr(response, "status", None))
        return _dict_payload(parsed)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[-1000:]
        receipts.log("descript_api", phase="finish", method=method, path=path, status_code=exc.code, error=detail)
        raise RuntimeError(f"descript_api_failed:{path}:{exc.code}") from exc


def _descript_upload(upload_url: str, audio_path: Path, receipts: Receipts) -> None:
    receipts.log("descript_upload", phase="start", media=DESCRIPT_MEDIA_NAME, bytes=audio_path.stat().st_size)
    request = urllib.request.Request(
        upload_url,
        data=audio_path.read_bytes(),
        headers={"Content-Type": "application/octet-stream"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            status_code = getattr(response, "status", None)
        receipts.log("descript_upload", phase="finish", media=DESCRIPT_MEDIA_NAME, status_code=status_code)
    except urllib.error.HTTPError as exc:
        receipts.log("descript_upload", phase="finish", media=DESCRIPT_MEDIA_NAME, status_code=exc.code)
        raise RuntimeError(f"descript_upload_failed:{exc.code}") from exc


def _wait_for_descript_job(job_id: str, token: str, receipts: Receipts, *, timeout_s: int = 1800) -> dict[str, Any]:
    started = time.monotonic()
    interval = float(os.environ.get("EDDY_V2_DESCRIPT_POLL_INTERVAL_S", "5"))
    while True:
        job = _descript_json_request("GET", f"/jobs/{job_id}", token, None, receipts)
        receipts.log("descript_job_poll", job=_redacted_job(job))
        if job.get("job_state") == "stopped":
            result = _dict_payload(job.get("result"))
            if result.get("status") != "success":
                raise RuntimeError(f"descript_job_failed:{job_id}:{result.get('status')}")
            return job
        if time.monotonic() - started > timeout_s:
            raise RuntimeError(f"descript_job_timeout:{job_id}")
        time.sleep(interval)


def _composition_id_from_import(import_job: dict[str, Any]) -> str:
    result = _dict_payload(import_job.get("result"))
    compositions = result.get("created_compositions")
    if not isinstance(compositions, list) or not compositions:
        raise RuntimeError("descript_import_missing_composition")
    first_composition = _dict_payload(compositions[0])
    composition_id = first_composition.get("id")
    if not composition_id:
        raise RuntimeError("descript_import_missing_composition_id")
    return str(composition_id)


def _download_descript_audio(publish_job: dict[str, Any], output: Path, receipts: Receipts) -> Path:
    result = _dict_payload(publish_job.get("result"))
    download_url = result.get("download_url") or publish_job.get("download_url")
    if not download_url:
        raise RuntimeError("descript_publish_missing_download_url")
    receipts.log(
        "descript_download",
        phase="start",
        media_type=result.get("media_type") or publish_job.get("media_type") or "Audio",
        expires_at=result.get("download_url_expires_at") or publish_job.get("download_url_expires_at"),
    )
    with urllib.request.urlopen(str(download_url), timeout=180) as response:
        output.write_bytes(response.read())
    receipts.log("descript_download", phase="finish", output=str(output), bytes=output.stat().st_size)
    return output


def _export_parity_passes(source_audio: Path, exported_audio: Path, receipts: Receipts) -> bool:
    source_duration = duration_s(source_audio)
    exported_duration = duration_s(exported_audio)
    delta = abs(source_duration - exported_duration)
    tolerance = max(1.0, source_duration * 0.01)
    status = "pass" if exported_audio.exists() and exported_duration > 0 and delta <= tolerance else "failed"
    receipts.log(
        "audio_descript_parity",
        status=status,
        source_duration_s=round(source_duration, 3),
        exported_duration_s=round(exported_duration, 3),
        delta_s=round(delta, 3),
        tolerance_s=round(tolerance, 3),
        uploaded_media="audio_extract_only",
    )
    return status == "pass"


def _fake_descript_studio_sound(extracted: Path, output: Path, receipts: Receipts) -> Path:
    receipts.log("descript_import", status="fake", uploaded_media="audio_extract_only", media=DESCRIPT_MEDIA_NAME)
    receipts.log("descript_agent", status="fake", prompt="Apply Studio Sound only. Do not edit timing or content.")
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(extracted),
            "-af",
            "highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=80,loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output),
        ],
        receipts,
        event="ffmpeg",
        timeout_s=900,
    )
    receipts.log("descript_publish", status="fake", media_type="Audio")
    receipts.log("descript_download", phase="finish", output=str(output), bytes=output.stat().st_size, fake=True)
    return output


def _try_descript_studio_sound(extracted: Path, run_dir: Path, receipts: Receipts, policy: RunPolicy, cost: CostTracker) -> Path | None:
    token = os.environ.get("DESCRIPT_API_KEY")
    if not token:
        receipts.log("audio_descript_parity", status="skipped", reason="DESCRIPT_API_KEY missing", uploaded_media="none")
        return None
    output = run_dir / "audio" / "descript-studio-sound.m4a"
    try:
        policy.require_cloud_allowed("descript", receipts)
        cost.charge("descript_studio_sound_estimate", 3.0, provider="descript")
        if os.environ.get("EDDY_V2_FAKE_DESCRIPT"):
            _fake_descript_studio_sound(extracted, output, receipts)
            return output if _export_parity_passes(extracted, output, receipts) else None

        import_payload = {
            "project_name": f"Eddy V2 Studio Sound {int(time.time())}",
            "add_media": {
                DESCRIPT_MEDIA_NAME: {
                    "content_type": "audio/wav",
                    "file_size": extracted.stat().st_size,
                }
            },
            "add_compositions": [{"name": "Studio Sound Audio", "clips": [{"media": DESCRIPT_MEDIA_NAME}]}],
        }
        import_response = _descript_json_request("POST", "/jobs/import/project_media", token, import_payload, receipts)
        upload_info = (import_response.get("upload_urls") or {}).get(DESCRIPT_MEDIA_NAME) or {}
        upload_url = upload_info.get("upload_url")
        if not upload_url:
            raise RuntimeError("descript_import_missing_upload_url")
        receipts.log(
            "descript_import",
            status="upload_url_received",
            job_id=import_response.get("job_id"),
            project_id=import_response.get("project_id"),
            project_url=import_response.get("project_url"),
            uploaded_media="audio_extract_only",
        )
        _descript_upload(str(upload_url), extracted, receipts)
        import_job = _wait_for_descript_job(str(import_response["job_id"]), token, receipts)
        composition_id = _composition_id_from_import(import_job)
        project_id = str(import_job.get("project_id") or import_response.get("project_id"))

        agent_payload = {
            "project_id": project_id,
            "composition_id": composition_id,
            "prompt": "Apply Studio Sound to the imported audio. Do not remove words, change timing, add captions, or alter content.",
        }
        agent_response = _descript_json_request("POST", "/jobs/agent", token, agent_payload, receipts)
        receipts.log("descript_agent", status="started", job_id=agent_response.get("job_id"), project_id=project_id)
        _wait_for_descript_job(str(agent_response["job_id"]), token, receipts)

        publish_payload = {
            "project_id": project_id,
            "composition_id": composition_id,
            "media_type": "Audio",
            "access_level": "private",
        }
        publish_response = _descript_json_request("POST", "/jobs/publish", token, publish_payload, receipts)
        receipts.log("descript_publish", status="started", job_id=publish_response.get("job_id"), project_id=project_id, media_type="Audio")
        publish_job = _wait_for_descript_job(str(publish_response["job_id"]), token, receipts)
        _download_descript_audio(publish_job, output, receipts)
        return output if _export_parity_passes(extracted, output, receipts) else None
    except Exception as exc:
        receipts.log("audio_descript_parity", status="failed", error=str(exc), uploaded_media="audio_extract_only")
        return None


def polish_audio(
    sources: Sources,
    run_dir: Path,
    receipts: Receipts,
    policy: RunPolicy,
    cost: CostTracker,
    *,
    start_s: float = 0.0,
    duration_s: float | None = None,
) -> Path:
    audio_dir = run_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    extracted = audio_dir / "source-audio.wav"
    extract_args = ["ffmpeg", "-y"]
    if start_s > 0:
        extract_args.extend(["-ss", f"{start_s:.3f}"])
    if duration_s is not None:
        extract_args.extend(["-t", f"{duration_s:.3f}"])
    extract_args.extend(["-i", str(sources.mic or sources.camera), "-vn", "-ac", "1", "-ar", "48000", str(extracted)])
    receipts.log(
        "audio_extract",
        source=str(sources.mic or sources.camera),
        start_s=round(start_s, 3),
        duration_s=round(duration_s, 3) if duration_s is not None else None,
        uploaded_media="audio_extract_only",
    )
    run_command(
        extract_args,
        receipts,
        event="ffmpeg",
        timeout_s=900,
    )

    descript_audio = _try_descript_studio_sound(extracted, run_dir, receipts, policy, cost)
    if descript_audio:
        receipts.log("audio_polish", status="pass", selected_backend="descript_studio_sound", output=str(descript_audio))
        return descript_audio

    for provider, env_name, charge in (
        ("auphonic", "AUPHONIC_API_KEY", 0.25),
        ("elevenlabs", "ELEVENLABS_API_KEY", 0.25),
    ):
        if os.environ.get(env_name):
            try:
                policy.require_cloud_allowed(provider, receipts)
                cost.charge(f"{provider}_audio_probe", charge, provider=provider)
                receipts.log("audio_cloud_backend", provider=provider, status="not_selected", reason="live adapter not enabled")
            except Exception as exc:
                receipts.log("audio_cloud_backend", provider=provider, status="failed", error=str(exc))
        else:
            receipts.log("audio_cloud_backend", provider=provider, status="skipped", reason=f"{env_name} missing")

    polished = audio_dir / "polished-audio.m4a"
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(extracted),
            "-af",
            "highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=80,loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(polished),
        ],
        receipts,
        event="ffmpeg",
        timeout_s=900,
    )
    receipts.log("audio_polish", status="pass", selected_backend="local_loudnorm_fallback", output=str(polished))
    return polished
