from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .commands import duration_s, run_command
from .cost import CostTracker
from .policy import RunPolicy
from .receipts import Receipts
from .sources import Sources


DESCRIPT_API_BASE = "https://descriptapi.com/v1"
DESCRIPT_MEDIA_NAME = "source-audio.wav"
AUPHONIC_API_BASE = "https://auphonic.com/api"
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"


def _descript_api_base() -> str:
    return os.environ.get("EDDY_V2_DESCRIPT_API_BASE", DESCRIPT_API_BASE).rstrip("/")


def _auphonic_api_base() -> str:
    return os.environ.get("EDDY_V2_AUPHONIC_API_BASE", AUPHONIC_API_BASE).rstrip("/")


def _elevenlabs_api_base() -> str:
    return os.environ.get("EDDY_V2_ELEVENLABS_API_BASE", ELEVENLABS_API_BASE).rstrip("/")


def _dict_payload(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _multipart_body(
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f"eddyv2-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode(),
                b"\r\n",
            ]
        )
    for name, (filename, data, content_type) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                data,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


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


def _audio_parity_passes(source_audio: Path, exported_audio: Path, receipts: Receipts, *, provider: str) -> bool:
    source_duration = duration_s(source_audio)
    exported_duration = duration_s(exported_audio)
    delta = abs(source_duration - exported_duration)
    tolerance = max(1.0, source_duration * 0.01)
    status = "pass" if exported_audio.exists() and exported_duration > 0 and delta <= tolerance else "failed"
    receipts.log(
        f"audio_{provider}_parity",
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


def _fake_cloud_audio(extracted: Path, output: Path, receipts: Receipts, *, provider: str) -> Path:
    receipts.log(f"{provider}_audio", status="fake", uploaded_media="audio_extract_only")
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(extracted),
            "-af",
            "highpass=f=80,afftdn=nf=-25,acompressor=threshold=-22dB:ratio=2.5:attack=8:release=120,loudnorm=I=-16:TP=-1.5:LRA=10",
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
            return output if _audio_parity_passes(extracted, output, receipts, provider="descript") else None

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
        return output if _audio_parity_passes(extracted, output, receipts, provider="descript") else None
    except Exception as exc:
        receipts.log("audio_descript_parity", status="failed", error=str(exc), uploaded_media="audio_extract_only")
        return None


def _auphonic_json_request(path: str, token: str, receipts: Receipts) -> dict[str, Any]:
    url = f"{_auphonic_api_base()}{path}"
    receipts.log("auphonic_api", phase="start", method="GET", path=path)
    request = urllib.request.Request(url, headers={"Authorization": f"bearer {token}"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        receipts.log("auphonic_api", phase="finish", method="GET", path=path, status_code=getattr(response, "status", None))
        return _dict_payload(parsed)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[-1000:]
        receipts.log("auphonic_api", phase="finish", method="GET", path=path, status_code=exc.code, error=detail)
        raise RuntimeError(f"auphonic_api_failed:{path}:{exc.code}") from exc


def _start_auphonic_simple(extracted: Path, token: str, preset: str, receipts: Receipts) -> str:
    fields = {
        "preset": preset,
        "title": f"Eddy V2 Audio Polish {int(time.time())}",
        "action": "start",
        "filtering": "true",
        "leveler": "true",
        "normloudness": "true",
        "loudnesstarget": "-16",
        "maxpeak": "-1",
        "denoise": "true",
        "denoiseamount": "12",
        "silence_cutter": "false",
        "filler_cutter": "false",
        "cough_cutter": "false",
        "music_cutter": "false",
    }
    body, content_type = _multipart_body(
        fields,
        {"input_file": (extracted.name, extracted.read_bytes(), "audio/wav")},
    )
    receipts.log("auphonic_upload", phase="start", uploaded_media="audio_extract_only", bytes=extracted.stat().st_size, preset_configured=True)
    request = urllib.request.Request(
        f"{_auphonic_api_base()}/simple/productions.json",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        payload = _dict_payload(parsed.get("data"))
        production_uuid = payload.get("uuid") or parsed.get("uuid")
        if not production_uuid:
            raise RuntimeError("auphonic_missing_production_uuid")
        receipts.log("auphonic_upload", phase="finish", status_code=getattr(response, "status", None), production_uuid=production_uuid)
        return str(production_uuid)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[-1000:]
        receipts.log("auphonic_upload", phase="finish", status_code=exc.code, error=detail)
        raise RuntimeError(f"auphonic_upload_failed:{exc.code}") from exc


def _wait_for_auphonic(production_uuid: str, token: str, receipts: Receipts, *, timeout_s: int = 1800) -> dict[str, Any]:
    started = time.monotonic()
    interval = float(os.environ.get("EDDY_V2_AUPHONIC_POLL_INTERVAL_S", "10"))
    while True:
        response = _auphonic_json_request(f"/production/{production_uuid}.json", token, receipts)
        production = _dict_payload(response.get("data"))
        status_string = str(production.get("status_string") or "")
        receipts.log("auphonic_job_poll", production_uuid=production_uuid, status=production.get("status"), status_string=status_string)
        if status_string.lower() == "done" or production.get("status") == 3:
            return production
        if production.get("error_status") or status_string.lower() in {"error", "failed"}:
            raise RuntimeError(f"auphonic_job_failed:{production_uuid}:{production.get('error_message') or status_string}")
        if time.monotonic() - started > timeout_s:
            raise RuntimeError(f"auphonic_job_timeout:{production_uuid}")
        time.sleep(interval)


def _download_auphonic_audio(production: dict[str, Any], token: str, output: Path, receipts: Receipts) -> Path:
    output_files = production.get("output_files")
    if not isinstance(output_files, list) or not output_files:
        raise RuntimeError("auphonic_missing_output_files")
    selected = _dict_payload(output_files[0])
    download_url = selected.get("download_url")
    if not download_url:
        raise RuntimeError("auphonic_missing_download_url")
    receipts.log(
        "auphonic_download",
        phase="start",
        production_uuid=production.get("uuid"),
        format=selected.get("format"),
        ending=selected.get("ending"),
        bytes=selected.get("size"),
    )
    parsed = urllib.parse.urlparse(str(download_url))
    headers = {"Authorization": f"bearer {token}"} if parsed.hostname and parsed.hostname.endswith("auphonic.com") else {}
    request = urllib.request.Request(str(download_url), headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=180) as response:
        output.write_bytes(response.read())
    receipts.log("auphonic_download", phase="finish", output=str(output), bytes=output.stat().st_size)
    return output


def _try_auphonic_polish(extracted: Path, run_dir: Path, receipts: Receipts, policy: RunPolicy, cost: CostTracker) -> Path | None:
    token = os.environ.get("AUPHONIC_API_KEY")
    if not token:
        receipts.log("audio_auphonic_parity", status="skipped", reason="AUPHONIC_API_KEY missing", uploaded_media="none")
        return None
    preset = os.environ.get("AUPHONIC_PRESET") or os.environ.get("AUPHONIC_PRESET_UUID")
    output = run_dir / "audio" / "auphonic-polished-audio.m4a"
    try:
        policy.require_cloud_allowed("auphonic", receipts)
        cost.charge("auphonic_audio_estimate", 1.0, provider="auphonic")
        if os.environ.get("EDDY_V2_FAKE_AUPHONIC"):
            _fake_cloud_audio(extracted, output, receipts, provider="auphonic")
            return output if _audio_parity_passes(extracted, output, receipts, provider="auphonic") else None
        if not preset:
            raise RuntimeError("AUPHONIC_PRESET missing")
        production_uuid = _start_auphonic_simple(extracted, token, preset, receipts)
        production = _wait_for_auphonic(production_uuid, token, receipts)
        _download_auphonic_audio(production, token, output, receipts)
        return output if _audio_parity_passes(extracted, output, receipts, provider="auphonic") else None
    except Exception as exc:
        receipts.log("audio_auphonic_parity", status="failed", error=str(exc), uploaded_media="audio_extract_only")
        return None


def _try_elevenlabs_isolation(extracted: Path, run_dir: Path, receipts: Receipts, policy: RunPolicy, cost: CostTracker) -> Path | None:
    token = os.environ.get("ELEVENLABS_API_KEY")
    if not token:
        receipts.log("audio_elevenlabs_parity", status="skipped", reason="ELEVENLABS_API_KEY missing", uploaded_media="none")
        return None
    output = run_dir / "audio" / "elevenlabs-isolated-audio.m4a"
    try:
        policy.require_cloud_allowed("elevenlabs", receipts)
        cost.charge("elevenlabs_audio_isolation_estimate", 1.0, provider="elevenlabs")
        if os.environ.get("EDDY_V2_FAKE_ELEVENLABS"):
            _fake_cloud_audio(extracted, output, receipts, provider="elevenlabs")
            return output if _audio_parity_passes(extracted, output, receipts, provider="elevenlabs") else None

        body, content_type = _multipart_body(
            {"file_format": "other"},
            {"audio": (extracted.name, extracted.read_bytes(), "audio/wav")},
        )
        receipts.log("elevenlabs_audio_isolation", phase="start", uploaded_media="audio_extract_only", bytes=extracted.stat().st_size)
        request = urllib.request.Request(
            f"{_elevenlabs_api_base()}/audio-isolation",
            data=body,
            headers={"xi-api-key": token, "Content-Type": content_type},
            method="POST",
        )
        raw_response = run_dir / "audio" / "elevenlabs-isolation-response.bin"
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                raw_response.write_bytes(response.read())
                content_type_response = response.headers.get("Content-Type")
            receipts.log(
                "elevenlabs_audio_isolation",
                phase="finish",
                status_code=getattr(response, "status", None),
                content_type=content_type_response,
                bytes=raw_response.stat().st_size,
            )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[-1000:]
            receipts.log("elevenlabs_audio_isolation", phase="finish", status_code=exc.code, error=detail)
            raise RuntimeError(f"elevenlabs_audio_isolation_failed:{exc.code}") from exc
        run_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(raw_response),
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
        return output if _audio_parity_passes(extracted, output, receipts, provider="elevenlabs") else None
    except Exception as exc:
        receipts.log("audio_elevenlabs_parity", status="failed", error=str(exc), uploaded_media="audio_extract_only")
        return None


def polish_extracted_audio(
    extracted: Path,
    run_dir: Path,
    receipts: Receipts,
    policy: RunPolicy,
    cost: CostTracker,
    *,
    allow_local_fallback: bool,
) -> Path | None:
    audio_dir = run_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    descript_audio = _try_descript_studio_sound(extracted, run_dir, receipts, policy, cost)
    if descript_audio:
        receipts.log("audio_polish", status="pass", selected_backend="descript_studio_sound", output=str(descript_audio))
        return descript_audio

    auphonic_audio = _try_auphonic_polish(extracted, run_dir, receipts, policy, cost)
    if auphonic_audio:
        receipts.log("audio_polish", status="pass", selected_backend="auphonic", output=str(auphonic_audio))
        return auphonic_audio

    elevenlabs_audio = _try_elevenlabs_isolation(extracted, run_dir, receipts, policy, cost)
    if elevenlabs_audio:
        receipts.log("audio_polish", status="pass", selected_backend="elevenlabs_audio_isolation", output=str(elevenlabs_audio))
        return elevenlabs_audio

    if not allow_local_fallback:
        receipts.log("audio_polish_retry", status="blocked", reason="no_cloud_audio_provider_passed", source_audio=str(extracted))
        return None

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

    polished = polish_extracted_audio(extracted, run_dir, receipts, policy, cost, allow_local_fallback=True)
    if polished is None:
        raise RuntimeError("audio_polish_missing")
    return polished
