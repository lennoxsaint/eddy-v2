from __future__ import annotations

import json
import sys
from pathlib import Path

from .pipeline import edit_folder

TOOLS = [
    {
        "name": "eddy_v2_edit_start",
        "description": "Start an Eddy V2 proof-gated edit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string"},
                "local_only": {"type": "boolean"},
                "cloud_budget": {"type": "number"},
                "target_duration": {"type": "number"},
            },
            "required": ["folder"],
        },
    },
    {
        "name": "eddy_v2_artifacts",
        "description": "List artifacts in a completed Eddy V2 run directory.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_dir": {"type": "string"}},
            "required": ["run_dir"],
        },
    },
]


def handle(method: str, params: dict) -> dict:
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "eddy_v2_edit_start":
            result = edit_folder(
                Path(args["folder"]),
                local_only=bool(args.get("local_only", False)),
                cloud_budget_usd=float(args.get("cloud_budget", 25.0)),
                target_duration_s=args.get("target_duration"),
            )
            return {"content": [{"type": "text", "text": json.dumps({"run_dir": str(result.run_dir), "status": result.status})}]}
        if name == "eddy_v2_artifacts":
            run_dir = Path(args["run_dir"])
            files = [str(p.relative_to(run_dir)) for p in run_dir.rglob("*") if p.is_file()]
            return {"content": [{"type": "text", "text": json.dumps({"run_dir": str(run_dir), "files": files})}]}
    raise ValueError(f"unsupported MCP method/tool: {method}")


def main() -> int:
    for line in sys.stdin:
        request = json.loads(line)
        try:
            result = handle(request.get("method", ""), request.get("params") or {})
            response = {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": request.get("id"), "error": {"code": -32000, "message": str(exc)}}
        print(json.dumps(response), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
