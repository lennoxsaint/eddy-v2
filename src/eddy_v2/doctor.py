from __future__ import annotations

import shutil
from collections.abc import Mapping
from typing import Callable

from . import __version__
from .cloud_quality import cloud_audio_profile, cloud_model_profile
from .identities import list_identities

REQUIRED_RUNTIME_TOOLS = ("ffmpeg", "ffprobe", "node", "npx")


def doctor_payload(which: Callable[[str], str | None] = shutil.which, environ: Mapping[str, str] | None = None) -> dict:
    tools = {tool: bool(which(tool)) for tool in REQUIRED_RUNTIME_TOOLS}
    missing = [tool for tool in REQUIRED_RUNTIME_TOOLS if not tools[tool]]
    return {
        "eddy_v2": __version__,
        **tools,
        "required_runtime_tools": tools,
        "missing_required_runtime_tools": missing,
        "ok": not missing,
        "cloud_quality_profile": {"audio": cloud_audio_profile(environ), "models": cloud_model_profile(environ)},
        "identities": list_identities(),
    }
