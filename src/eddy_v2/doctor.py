from __future__ import annotations

import shutil
from typing import Callable

from . import __version__
from .identities import list_identities

REQUIRED_RUNTIME_TOOLS = ("ffmpeg", "ffprobe", "node", "npx")


def doctor_payload(which: Callable[[str], str | None] = shutil.which) -> dict:
    tools = {tool: bool(which(tool)) for tool in REQUIRED_RUNTIME_TOOLS}
    missing = [tool for tool in REQUIRED_RUNTIME_TOOLS if not tools[tool]]
    return {
        "eddy_v2": __version__,
        **tools,
        "required_runtime_tools": tools,
        "missing_required_runtime_tools": missing,
        "ok": not missing,
        "identities": list_identities(),
    }
