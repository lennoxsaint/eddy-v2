#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

REQUIRED_IDENTITIES = {
    "threadify-fc",
    "code-cinema",
    "liquid-glass",
    "broadcast-receipts",
    "kinetic-poster",
    "editorial-data",
}

REQUIRED_CLI = {
    "doctor",
    "edit",
    "status",
    "artifacts",
    "scorecard",
    "bakeoff",
    "review",
    "audio-proof",
}

REQUIRED_MCP = {
    "eddy_v2_doctor",
    "eddy_v2_edit_start",
    "eddy_v2_status",
    "eddy_v2_artifacts",
    "eddy_v2_scorecard",
    "eddy_v2_bakeoff",
    "eddy_v2_review",
    "eddy_v2_audio_proof",
}

REQUIRED_DOCS = [
    ROOT / "README.md",
    ROOT / "CONTEXT.md",
    ROOT / "docs" / "adr" / "0001-separate-public-v2-repo.md",
    ROOT / "docs" / "adr" / "0002-cloud-first-receipts.md",
    ROOT / "docs" / "adr" / "0003-hyperframes-identities.md",
    ROOT / "docs" / "adr" / "0004-descript-verified-audio.md",
    ROOT / "docs" / "BAKEOFF.md",
    ROOT / "skills" / "eddy-v2" / "SKILL.md",
    ROOT / "mcp" / "eddy-v2.config.json",
]

REQUIRED_CONTEXT_TERMS = [
    "Proof-Gated One-Command",
    "Identity Pack",
    "Cloud Quality Profile",
    "Quarantined Partial",
    "Bakeoff Hero Video",
]

REQUIRED_PACKAGE_DATA = {
    "identities_data/*/*",
    "identities_data/*/assets/*",
}

REQUIRED_THREADIFY_FC_ASSETS = {
    "agent-keyed.png",
    "done-keyed.png",
    "fc-ring.png",
    "hero-keyed.png",
    "receipt-keyed.png",
    "stuck-keyed.png",
    "think-keyed.png",
    "threadify-needle.png",
}

PERMISSIVE_BUILD_DEPS = {"setuptools", "wheel"}
PERMISSIVE_DEV_DEPS = {"mypy", "pytest", "pytest-cov", "ruff"}

FORBIDDEN_PUBLICATION_PATTERNS = {
    "google_youtube_upload": re.compile(r"googleapiclient|youtube_upload|videos\\.insert", re.IGNORECASE),
    "social_publish_action": re.compile(r"publish_now|schedule_post|send_reply|post_to_(?:x|twitter|threads|linkedin|instagram)", re.IGNORECASE),
    "social_platform_sdk": re.compile(r"\\btweepy\\b|\\binstagrapi\\b|\\blinkedin\\b|\\btiktok\\b", re.IGNORECASE),
}


def _project() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _name(requirement: str) -> str:
    return re.split(r"[<>=!~ ]", requirement, maxsplit=1)[0].strip()


def _subcommands() -> set[str]:
    sys.path.insert(0, str(SRC))
    cli = importlib.import_module("eddy_v2.cli")
    parser = cli.build_parser()
    for action in parser._actions:  # argparse exposes subparsers only through private slots.
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict):
            return set(choices)
    return set()


def _mcp_tools() -> set[str]:
    sys.path.insert(0, str(SRC))
    mcp = importlib.import_module("eddy_v2.mcp_server")
    return {str(tool["name"]) for tool in mcp.TOOLS}


def _identity_slugs() -> set[str]:
    sys.path.insert(0, str(SRC))
    identities = importlib.import_module("eddy_v2.identities")
    return set(identities.list_identities())


def _scan_publication_integrations() -> list[str]:
    findings: list[str] = []
    for root in (ROOT / "src", ROOT / "scripts"):
        for path in root.rglob("*"):
            if path.resolve() == Path(__file__).resolve():
                continue
            if path.suffix not in {".py", ".json", ".toml"} or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for label, pattern in FORBIDDEN_PUBLICATION_PATTERNS.items():
                if pattern.search(text):
                    findings.append(f"{path.relative_to(ROOT)} matched {label}")
    return findings


def main() -> int:
    project = _project()
    runtime_deps = [_name(dep) for dep in project.get("project", {}).get("dependencies", [])]
    dev_deps = {_name(dep) for dep in project.get("project", {}).get("optional-dependencies", {}).get("dev", [])}
    build_deps = {_name(dep) for dep in project.get("build-system", {}).get("requires", [])}
    subcommands = _subcommands()
    mcp_tools = _mcp_tools()
    identity_slugs = _identity_slugs()
    package_data = set(project.get("tool", {}).get("setuptools", {}).get("package-data", {}).get("eddy_v2", []))
    threadify_fc_assets = {
        path.name for path in (SRC / "eddy_v2" / "identities_data" / "threadify-fc" / "assets").glob("*.png")
    }
    context = (ROOT / "CONTEXT.md").read_text(encoding="utf-8")
    forbidden_publication = _scan_publication_integrations()

    checks = {
        "mit_license": (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")
        and project.get("project", {}).get("license") == "MIT",
        "no_runtime_dependencies": runtime_deps == [],
        "permissive_build_and_dev_dependencies": build_deps <= PERMISSIVE_BUILD_DEPS and dev_deps <= PERMISSIVE_DEV_DEPS,
        "required_cli_surface": REQUIRED_CLI <= subcommands,
        "required_mcp_surface": REQUIRED_MCP <= mcp_tools,
        "frozen_identity_pack": identity_slugs == REQUIRED_IDENTITIES,
        "required_docs_present": all(path.exists() for path in REQUIRED_DOCS),
        "required_context_terms": all(term in context for term in REQUIRED_CONTEXT_TERMS),
        "identity_assets_packaged": REQUIRED_PACKAGE_DATA <= package_data,
        "required_threadify_fc_assets_present": threadify_fc_assets == REQUIRED_THREADIFY_FC_ASSETS,
        "no_hosted_app_dependencies": not any(dep in runtime_deps or dep in dev_deps for dep in {"flask", "fastapi", "django", "streamlit", "uvicorn"}),
        "no_public_publish_integrations": forbidden_publication == [],
    }
    payload = {
        "status": "pass" if all(checks.values()) else "failed",
        "checks": checks,
        "details": {
            "runtime_dependencies": runtime_deps,
            "dev_dependencies": sorted(dev_deps),
            "build_dependencies": sorted(build_deps),
            "cli_subcommands": sorted(subcommands),
            "mcp_tools": sorted(mcp_tools),
            "identities": sorted(identity_slugs),
            "package_data": sorted(package_data),
            "threadify_fc_assets": sorted(threadify_fc_assets),
            "forbidden_publication_findings": forbidden_publication,
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
