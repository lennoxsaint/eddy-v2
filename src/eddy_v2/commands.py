from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Sequence

from .receipts import Receipts


def run_command(
    args: Sequence[str],
    receipts: Receipts,
    *,
    event: str,
    cwd: Path | None = None,
    timeout_s: int | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    safe_args = [str(a) for a in args]
    receipts.log(event, phase="start", argv=safe_args, cwd=str(cwd) if cwd else None)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        safe_args,
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_s,
        env=merged_env,
    )
    receipts.log(
        event,
        phase="finish",
        argv=safe_args,
        returncode=proc.returncode,
        stdout_tail=proc.stdout[-2000:],
        stderr_tail=proc.stderr[-2000:],
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"{event}_failed: {safe_args} -> {proc.returncode}")
    return proc


def ffprobe_json(path: Path) -> dict:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=index,codec_type,width,height,avg_frame_rate,r_frame_rate,channels,sample_rate",
            "-of",
            "json",
            str(path),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return json.loads(proc.stdout)


def duration_s(path: Path) -> float:
    data = ffprobe_json(path)
    return float(data.get("format", {}).get("duration") or 0.0)
