#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SECRET_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{24,}")),
    (
        "env_secret_assignment",
        re.compile(
            r"\b(?:OPENROUTER_API_KEY|DESCRIPT_API_KEY|AUPHONIC_API_KEY|ELEVENLABS_API_KEY)\s*=\s*['\"]?[A-Za-z0-9._~+/=-]{12,}"
        ),
    ),
]

TEXT_EXTENSIONS = {
    ".css",
    ".html",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}


def tracked_files() -> list[Path]:
    proc = subprocess.run(["git", "ls-files"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return [Path(line) for line in proc.stdout.splitlines() if line]


def should_scan(path: Path) -> bool:
    if path.suffix in TEXT_EXTENSIONS:
        return True
    return path.name in {"LICENSE", ".gitignore"}


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        if not should_scan(path) or not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"{path}: matched {name}")
    if findings:
        print("public scrub failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("public scrub passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
