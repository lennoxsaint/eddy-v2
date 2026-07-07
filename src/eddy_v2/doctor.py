from __future__ import annotations

import shutil
import subprocess
from collections.abc import Mapping
from typing import Callable

from . import __version__
from .cloud_quality import cloud_audio_profile, cloud_model_profile
from .identities import list_identities
from .motion import NODE_RENDERER

REQUIRED_RUNTIME_TOOLS = ("ffmpeg", "ffprobe", "node", "npx")


def onepassword_cli_status(
    which: Callable[[str], str | None] = shutil.which,
    *,
    timeout_s: float = 2.0,
    op_whoami: Callable[[], tuple[int, str, str]] | None = None,
) -> dict:
    op = which("op")
    if not op:
        return {"installed": False, "signed_in": False, "status": "missing", "check": "op whoami"}
    if op_whoami is None:
        try:
            proc = subprocess.run([op, "whoami"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_s)
            result = (proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired:
            return {"installed": True, "signed_in": False, "status": "timeout", "check": "op whoami"}
        except OSError as exc:
            return {"installed": True, "signed_in": False, "status": "unavailable", "check": "op whoami", "error": str(exc)}
    else:
        result = op_whoami()
    returncode, _stdout, stderr = result
    if returncode == 0:
        return {"installed": True, "signed_in": True, "status": "signed_in", "check": "op whoami"}
    if "not signed in" in stderr.lower():
        return {"installed": True, "signed_in": False, "status": "not_signed_in", "check": "op whoami"}
    return {"installed": True, "signed_in": False, "status": "unavailable", "check": "op whoami"}


def doctor_payload(
    which: Callable[[str], str | None] = shutil.which,
    environ: Mapping[str, str] | None = None,
    *,
    check_onepassword: bool = False,
    op_whoami: Callable[[], tuple[int, str, str]] | None = None,
) -> dict:
    tools = {tool: bool(which(tool)) for tool in REQUIRED_RUNTIME_TOOLS}
    missing = [tool for tool in REQUIRED_RUNTIME_TOOLS if not tools[tool]]
    return {
        "eddy_v2": __version__,
        **tools,
        "required_runtime_tools": tools,
        "missing_required_runtime_tools": missing,
        "ok": not missing,
        "node_renderer": {
            "adapter": str(NODE_RENDERER),
            "exists": NODE_RENDERER.exists(),
            "script": "npm run renderer:doctor",
        },
        "cloud_quality_profile": {"audio": cloud_audio_profile(environ), "models": cloud_model_profile(environ)},
        "credential_helpers": {
            "onepassword_cli": onepassword_cli_status(which, op_whoami=op_whoami) if check_onepassword else {"status": "not_checked", "check": "op whoami"},
        },
        "identities": list_identities(),
    }
