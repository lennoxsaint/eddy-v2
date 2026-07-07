from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .receipts import Receipts

VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".flac"}


@dataclass(frozen=True)
class Sources:
    folder: Path
    camera: Path
    screen: Path | None = None
    mic: Path | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "folder": str(self.folder),
            "camera": str(self.camera),
            "screen": str(self.screen) if self.screen else None,
            "mic": str(self.mic) if self.mic else None,
        }


def discover_sources(folder: Path) -> Sources:
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"footage folder not found: {folder}")

    videos = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES)
    audios = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES)
    if not videos:
        raise FileNotFoundError(f"no video sources found in {folder}")

    def pick(names: tuple[str, ...], candidates: list[Path]) -> Path | None:
        for candidate in candidates:
            stem = candidate.stem.lower()
            if any(name in stem for name in names):
                return candidate
        return None

    camera = pick(("camera", "cam", "face", "webcam", "talking"), videos) or videos[0]
    screen = pick(("screen", "display", "slide", "desktop"), [p for p in videos if p != camera])
    mic = pick(("mic", "audio", "studio", "voice"), audios)
    return Sources(folder=folder, camera=camera, screen=screen, mic=mic)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024 * 8), b""):
            digest.update(chunk)
    return digest.hexdigest()


def lock_sources(sources: Sources, receipts: Receipts, *, phase: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for label, value in (("camera", sources.camera), ("screen", sources.screen), ("mic", sources.mic)):
        if value is None:
            continue
        hashes[label] = sha256_file(value)
        receipts.log("source_hash", phase=phase, label=label, path=str(value), sha256=hashes[label])
    return hashes


def write_manifest(run_dir: Path, sources: Sources, before_hashes: dict[str, str]) -> None:
    manifest = {"sources": sources.as_dict(), "source_sha256_before": before_hashes}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
