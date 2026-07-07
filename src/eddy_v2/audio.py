from __future__ import annotations

import os
from pathlib import Path

from .commands import run_command
from .cost import CostTracker
from .policy import RunPolicy
from .receipts import Receipts
from .sources import Sources


def polish_audio(sources: Sources, run_dir: Path, receipts: Receipts, policy: RunPolicy, cost: CostTracker) -> Path:
    audio_dir = run_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    extracted = audio_dir / "source-audio.wav"
    run_command(
        ["ffmpeg", "-y", "-i", str(sources.mic or sources.camera), "-vn", "-ac", "1", "-ar", "48000", str(extracted)],
        receipts,
        event="ffmpeg",
        timeout_s=900,
    )

    descript_key = os.environ.get("DESCRIPT_API_KEY")
    if descript_key:
        try:
            policy.require_cloud_allowed("descript", receipts)
            cost.charge("descript_probe", 0.50, provider="descript")
            receipts.log(
                "audio_descript_parity",
                status="blocked",
                reason="adapter scaffold present; live Descript upload/export not enabled in this build",
                uploaded_media="audio_extract_only",
            )
        except Exception as exc:
            receipts.log("audio_descript_parity", status="failed", error=str(exc))
    else:
        receipts.log("audio_descript_parity", status="skipped", reason="DESCRIPT_API_KEY missing", uploaded_media="none")

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
