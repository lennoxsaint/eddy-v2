from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import __version__


ROOT = Path(__file__).resolve().parents[2]


def _git(args: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = proc.stdout.strip()
    return value or None


def build_provenance(*, local_only: bool, cloud_budget_usd: float, target_duration_s: float | None) -> dict[str, Any]:
    commit = os.environ.get("EDDY_V2_BUILD_SHA") or _git(["rev-parse", "HEAD"])
    branch = os.environ.get("EDDY_V2_BUILD_BRANCH") or _git(["branch", "--show-current"])
    status = _git(["status", "--porcelain"])
    remote = _git(["config", "--get", "remote.origin.url"])
    return {
        "eddy_v2_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "python_executable": sys.executable,
        "package_root": str(Path(__file__).resolve().parent),
        "git": {
            "repo_root": str(ROOT),
            "commit": commit,
            "branch": branch,
            "dirty": bool(status),
            "remote_origin": remote,
            "available": commit is not None,
        },
        "run_settings": {
            "local_only": local_only,
            "cloud_budget_usd": cloud_budget_usd,
            "target_duration_s": target_duration_s,
        },
        "renderer_boundary": {
            "node_adapter": "renderer/hyperframes-runner.mjs",
            "hyperframes_default": True,
        },
    }
