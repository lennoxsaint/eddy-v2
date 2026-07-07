from __future__ import annotations

from dataclasses import dataclass

from .receipts import Receipts

CLOUD_SURFACES = ("openrouter", "descript", "auphonic", "elevenlabs", "cloud_render", "image_upload")


@dataclass(frozen=True)
class RunPolicy:
    local_only: bool = False
    cloud_budget_usd: float = 25.0

    def require_cloud_allowed(self, surface: str, receipts: Receipts) -> None:
        if surface not in CLOUD_SURFACES:
            raise ValueError(f"unknown cloud surface: {surface}")
        if self.local_only:
            receipts.log("cloud_refused", surface=surface, reason="local_only")
            raise RuntimeError(f"cloud_refused:{surface}")
        receipts.log("cloud_allowed", surface=surface, budget_usd=self.cloud_budget_usd)
