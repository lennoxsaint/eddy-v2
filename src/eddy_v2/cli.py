from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from .identities import list_identities
from .pipeline import edit_folder
from .receipts import Receipts


def doctor(_args: argparse.Namespace) -> int:
    checks = {
        "eddy_v2": __version__,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "node": bool(shutil.which("node")),
        "npx": bool(shutil.which("npx")),
        "identities": list_identities(),
    }
    print(json.dumps(checks, indent=2))
    return 0 if checks["ffmpeg"] and checks["ffprobe"] else 1


def edit(args: argparse.Namespace) -> int:
    result = edit_folder(
        Path(args.folder),
        local_only=args.local_only,
        cloud_budget_usd=args.cloud_budget,
        target_duration_s=args.target_duration,
    )
    print(json.dumps({"run_dir": str(result.run_dir), "status": result.status, "blockers": result.blockers}, indent=2))
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
    path = Path(args.run_dir) / "scorecard.md"
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
    )
    bakeoff_path = result.run_dir / "bakeoff.md"
    bakeoff_path.write_text(
        "# Eddy V2 Bakeoff\n\n"
        f"- hero_folder: {Path(args.folder).resolve()}\n"
        f"- v2_status: {result.status}\n"
        "- current_eddy_output: not compared by this command unless provided externally\n"
        "- winner_bar: pending Lennox 8/10 review\n",
        encoding="utf-8",
    )
    print(json.dumps({"run_dir": str(result.run_dir), "bakeoff": str(bakeoff_path), "status": result.status}, indent=2))
    return 0 if result.status == "complete" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eddy", description="Eddy V2 proof-gated editor")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(func=doctor)
    for name, func in (("edit", edit), ("bakeoff", bakeoff)):
        p = sub.add_parser(name)
        p.add_argument("folder")
        p.add_argument("--local-only", action="store_true")
        p.add_argument("--cloud-budget", type=float, default=25.0)
        p.add_argument("--target-duration", type=float, default=None)
        p.set_defaults(func=func)
    for name, func in (("status", status), ("artifacts", artifacts), ("scorecard", scorecard)):
        p = sub.add_parser(name)
        p.add_argument("run_dir")
        p.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
