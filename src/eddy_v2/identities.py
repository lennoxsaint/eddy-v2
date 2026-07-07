from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

SLUGS = (
    "threadify-fc",
    "code-cinema",
    "liquid-glass",
    "broadcast-receipts",
    "kinetic-poster",
    "editorial-data",
)


@dataclass(frozen=True)
class Identity:
    slug: str
    root: Path

    @property
    def frame_md(self) -> Path:
        return self.root / "frame.md"

    @property
    def css(self) -> Path:
        return self.root / "identity.css"

    @property
    def blocks(self) -> list[dict]:
        path = self.root / "blocks.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("blocks", [])
        return []


def identities_root() -> Path:
    return Path(str(files("eddy_v2") / "identities_data"))


def list_identities() -> list[str]:
    root = identities_root()
    return [slug for slug in SLUGS if (root / slug / "frame.md").exists()]


def load_identity(slug: str) -> Identity:
    if slug not in SLUGS:
        raise ValueError(f"unknown identity slug: {slug}")
    root = identities_root() / slug
    required = [root / "frame.md", root / "identity.css", root / "blocks.json"]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(f"identity {slug} is incomplete: {missing}")
    return Identity(slug=slug, root=root)
