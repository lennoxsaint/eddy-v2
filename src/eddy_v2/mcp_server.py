from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .audio_retry import retry_audio_proof
from .bakeoff import build_bakeoff_report
from .doctor import doctor_payload
from .pipeline import edit_folder
from .quality_review import apply_quality_review
from .receipts import Receipts
from .run_summary import build_run_output_payload

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "eddy-v2", "version": "0.1.0"}

TOOLS = [
    {
        "name": "eddy_v2_doctor",
        "description": "Check the local Eddy V2 runtime and installed media dependencies.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
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
                "intent": {"type": "object"},
                "intent_json": {"type": "string"},
            },
            "required": ["folder"],
        },
    },
    {
        "name": "eddy_v2_status",
        "description": "Read a run scorecard if present, otherwise return recent receipts.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_dir": {"type": "string"}},
            "required": ["run_dir"],
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
    {
        "name": "eddy_v2_scorecard",
        "description": "Read the human-facing Markdown scorecard for a run.",
        "inputSchema": {
            "type": "object",
            "properties": {"run_dir": {"type": "string"}},
            "required": ["run_dir"],
        },
    },
    {
        "name": "eddy_v2_bakeoff",
        "description": "Run Eddy V2 on raw footage and write a bakeoff report against current Eddy proof.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string"},
                "local_only": {"type": "boolean"},
                "cloud_budget": {"type": "number"},
                "target_duration": {"type": "number"},
                "current_run": {"type": "string"},
                "intent": {"type": "object"},
                "intent_json": {"type": "string"},
            },
            "required": ["folder"],
        },
    },
    {
        "name": "eddy_v2_review",
        "description": "Record Lennox's 8/10 quality review scores for a completed run.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_dir": {"type": "string"},
                "long_edit": {"type": "number"},
                "motion": {"type": "number"},
                "audio": {"type": "number"},
                "shorts": {"type": "number"},
                "reviewer": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["run_dir", "long_edit", "motion", "audio", "shorts"],
        },
    },
    {
        "name": "eddy_v2_audio_proof",
        "description": "Retry cloud audio proof for an existing run using only the extracted WAV, then remux the final long video if Strong Studio Sound passes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_dir": {"type": "string"},
                "local_only": {"type": "boolean"},
                "cloud_budget": {"type": "number"},
            },
            "required": ["run_dir"],
        },
    },
]


def _json_content(payload: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def _text_content(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _doctor_payload() -> dict[str, Any]:
    return doctor_payload(check_onepassword=True)


def _status_payload(run_dir: Path) -> dict[str, Any]:
    score = run_dir / "scorecard.json"
    if score.exists():
        parsed = json.loads(score.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            return parsed
    receipts = Receipts(run_dir / "receipts.jsonl").read_all()
    return {"run_dir": str(run_dir), "receipts": receipts[-5:]}


def _artifacts_payload(run_dir: Path) -> dict[str, Any]:
    files = sorted(str(p.relative_to(run_dir)) for p in run_dir.rglob("*") if p.is_file())
    return {"run_dir": str(run_dir), "files": files}


def _scorecard_text(run_dir: Path) -> str:
    path = run_dir / "scorecard.md"
    if not path.exists():
        raise FileNotFoundError(f"scorecard not found: {path}")
    return path.read_text(encoding="utf-8")


def _host_intent_payload(args: dict[str, Any]) -> dict[str, Any] | None:
    if "intent" in args and args["intent"] is not None:
        intent = args["intent"]
        if not isinstance(intent, dict):
            raise ValueError("intent must be a JSON object")
        return intent
    if args.get("intent_json"):
        parsed = json.loads(str(args["intent_json"]))
        if not isinstance(parsed, dict):
            raise ValueError("intent_json must decode to a JSON object")
        return parsed
    return None


def _edit_payload(args: dict[str, Any]) -> dict[str, Any]:
    result = edit_folder(
        Path(args["folder"]),
        local_only=bool(args.get("local_only", False)),
        cloud_budget_usd=float(args.get("cloud_budget", 25.0)),
        target_duration_s=args.get("target_duration"),
        host_intent_payload=_host_intent_payload(args),
    )
    return build_run_output_payload(result.run_dir, status=result.status, blockers=result.blockers)


def _bakeoff_payload(args: dict[str, Any]) -> dict[str, Any]:
    result = edit_folder(
        Path(args["folder"]),
        local_only=bool(args.get("local_only", False)),
        cloud_budget_usd=float(args.get("cloud_budget", 25.0)),
        target_duration_s=args.get("target_duration"),
        host_intent_payload=_host_intent_payload(args),
    )
    report = build_bakeoff_report(
        folder=Path(args["folder"]),
        v2_run_dir=result.run_dir,
        current_run_dir=Path(args["current_run"]) if args.get("current_run") else None,
        receipts=Receipts(result.run_dir / "receipts.jsonl"),
    )
    return {
        **build_run_output_payload(result.run_dir, status=result.status, blockers=result.blockers),
        "bakeoff": str(result.run_dir / "bakeoff.md"),
        "bakeoff_json": str(result.run_dir / "bakeoff.json"),
        "current_output_proof": report["current_output_proof"],
        "winner": report["winner"],
        "remaining_blockers": report["completion_audit"]["remaining_blockers"],
    }


def _review_payload(args: dict[str, Any]) -> dict[str, Any]:
    return apply_quality_review(
        Path(args["run_dir"]),
        {
            "long_edit_story": float(args["long_edit"]),
            "motion_graphics": float(args["motion"]),
            "audio_polish": float(args["audio"]),
            "shorts_watchability": float(args["shorts"]),
        },
        reviewer=str(args.get("reviewer") or "Lennox"),
        notes=str(args.get("notes") or ""),
    )


def _audio_proof_payload(args: dict[str, Any]) -> dict[str, Any]:
    return retry_audio_proof(
        Path(args["run_dir"]),
        local_only=bool(args.get("local_only", False)),
        cloud_budget_usd=float(args.get("cloud_budget", 25.0)),
    )


def _initialize_payload(params: dict[str, Any]) -> dict[str, Any]:
    requested_version = params.get("protocolVersion")
    protocol_version = str(requested_version) if requested_version else PROTOCOL_VERSION
    return {
        "protocolVersion": protocol_version,
        "capabilities": {"tools": {}},
        "serverInfo": SERVER_INFO,
    }


def handle(method: str, params: dict[str, Any]) -> dict[str, Any] | None:
    if method == "initialize":
        return _initialize_payload(params)
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "eddy_v2_doctor":
            return _json_content(_doctor_payload())
        if name == "eddy_v2_edit_start":
            return _json_content(_edit_payload(args))
        if name == "eddy_v2_status":
            return _json_content(_status_payload(Path(args["run_dir"])))
        if name == "eddy_v2_artifacts":
            return _json_content(_artifacts_payload(Path(args["run_dir"])))
        if name == "eddy_v2_scorecard":
            return _text_content(_scorecard_text(Path(args["run_dir"])))
        if name == "eddy_v2_bakeoff":
            return _json_content(_bakeoff_payload(args))
        if name == "eddy_v2_review":
            return _json_content(_review_payload(args))
        if name == "eddy_v2_audio_proof":
            return _json_content(_audio_proof_payload(args))
    raise ValueError(f"unsupported MCP method/tool: {method}")


def main() -> int:
    for line in sys.stdin:
        request = json.loads(line)
        request_id = request.get("id")
        try:
            result = handle(request.get("method", ""), request.get("params") or {})
            if request_id is None:
                continue
            response = {"jsonrpc": "2.0", "id": request_id, "result": result or {}}
        except Exception as exc:
            if request_id is None:
                continue
            response = {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}
        print(json.dumps(response), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
