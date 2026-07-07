from __future__ import annotations

import argparse
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


def load_intent_payload(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"intent payload must be a JSON object: {path}")
    return parsed


def doctor(_args: argparse.Namespace) -> int:
    checks = doctor_payload()
    print(json.dumps(checks, indent=2))
    return 0 if checks["ok"] else 1


def edit(args: argparse.Namespace) -> int:
    result = edit_folder(
        Path(args.folder),
        local_only=args.local_only,
        cloud_budget_usd=args.cloud_budget,
        target_duration_s=args.target_duration,
        host_intent_payload=load_intent_payload(args.intent),
    )
    print(json.dumps(build_run_output_payload(result.run_dir, status=result.status, blockers=result.blockers), indent=2))
    return 0 if result.status == "complete" else 2


def status(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    score = run_dir / "scorecard.json"
    if score.exists():
        print(score.read_text(encoding="utf-8"))
        return 0
    receipts = Receipts(run_dir / "receipts.jsonl").read_all()
    print(json.dumps({"run_dir": str(run_dir), "receipts": receipts[-5:]}, indent=2))
    return 0


def artifacts(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    files = sorted(str(p.relative_to(run_dir)) for p in run_dir.rglob("*") if p.is_file())
    print(json.dumps({"run_dir": str(run_dir), "files": files}, indent=2))
    return 0


def scorecard(args: argparse.Namespace) -> int:
    suffix = "json" if args.json else "md"
    path = Path(args.run_dir) / f"scorecard.{suffix}"
    if not path.exists():
        print(f"scorecard not found: {path}", file=sys.stderr)
        return 1
    print(path.read_text(encoding="utf-8"))
    return 0


def bakeoff(args: argparse.Namespace) -> int:
    result = edit_folder(
        Path(args.folder),
        local_only=args.local_only,
        cloud_budget_usd=args.cloud_budget,
        target_duration_s=args.target_duration,
        host_intent_payload=load_intent_payload(args.intent),
    )
    report = build_bakeoff_report(
        folder=Path(args.folder),
        v2_run_dir=result.run_dir,
        current_run_dir=Path(args.current_run) if args.current_run else None,
        receipts=Receipts(result.run_dir / "receipts.jsonl"),
    )
    print(
        json.dumps(
            {
                **build_run_output_payload(result.run_dir, status=result.status, blockers=result.blockers),
                "bakeoff": str(result.run_dir / "bakeoff.md"),
                "bakeoff_json": str(result.run_dir / "bakeoff.json"),
                "current_output_proof": report["current_output_proof"],
                "winner": report["winner"],
                "remaining_blockers": report["completion_audit"]["remaining_blockers"],
            },
            indent=2,
        )
    )
    return 0 if result.status == "complete" else 2


def review(args: argparse.Namespace) -> int:
    result = apply_quality_review(
        Path(args.run_dir),
        {
            "long_edit_story": args.long_edit,
            "motion_graphics": args.motion,
            "audio_polish": args.audio,
            "shorts_watchability": args.shorts,
        },
        reviewer=args.reviewer,
        notes=args.notes or "",
    )
    print(json.dumps(result, indent=2))
    return 0 if result["publishable_8_of_10"] else 2


def audio_proof(args: argparse.Namespace) -> int:
    result = retry_audio_proof(
        Path(args.run_dir),
        local_only=args.local_only,
        cloud_budget_usd=args.cloud_budget,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eddy", description="Eddy V2 proof-gated editor")
    sub = parser.add_subparsers(dest="cmd", required=True)
    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
    doctor_parser.set_defaults(func=doctor)
    for name, func in (("edit", edit), ("bakeoff", bakeoff)):
        p = sub.add_parser(name)
        p.add_argument("folder")
        p.add_argument("--local-only", action="store_true")
        p.add_argument("--cloud-budget", type=float, default=25.0)
        p.add_argument("--target-duration", type=float, default=None)
        p.add_argument("--intent", default=None, help="Path to a host-agent EditIntent JSON object")
        if name == "bakeoff":
            p.add_argument("--current-run", default=None)
        p.set_defaults(func=func)
    for name, func in (("status", status), ("artifacts", artifacts), ("scorecard", scorecard)):
        p = sub.add_parser(name)
        p.add_argument("run_dir")
        p.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
        p.set_defaults(func=func)
    p = sub.add_parser("review")
    p.add_argument("run_dir")
    p.add_argument("--long-edit", type=float, required=True)
    p.add_argument("--motion", type=float, required=True)
    p.add_argument("--audio", type=float, required=True)
    p.add_argument("--shorts", type=float, required=True)
    p.add_argument("--reviewer", default="Lennox")
    p.add_argument("--notes", default="")
    p.set_defaults(func=review)
    p = sub.add_parser("audio-proof")
    p.add_argument("run_dir")
    p.add_argument("--local-only", action="store_true")
    p.add_argument("--cloud-budget", type=float, default=25.0)
    p.set_defaults(func=audio_proof)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
