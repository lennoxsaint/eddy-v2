from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .commands import duration_s
from .cost import CostTracker
from .identities import SLUGS
from .policy import RunPolicy
from .receipts import Receipts
from .sources import Sources


@dataclass(frozen=True)
class EditIntent:
    target_duration_s: float
    identity: str
    shorts_target: int
    hook: str
    title: str

    def as_dict(self) -> dict:
        return {
            "target_duration_s": self.target_duration_s,
            "identity": self.identity,
            "shorts_target": self.shorts_target,
            "hook": self.hook,
            "title": self.title,
        }


def default_intent(sources: Sources, *, target_duration_s: float | None = None) -> EditIntent:
    source_duration = duration_s(sources.camera)
    requested_duration = target_duration_s or 600.0
    duration = max(1.0, min(requested_duration, source_duration))
    return EditIntent(
        target_duration_s=duration,
        identity="code-cinema" if sources.screen else "kinetic-poster",
        shorts_target=3,
        hook="The fastest path from raw footage to proof-gated video",
        title="Codex Custom Models: Proof-Gated Edit",
    )


def _clamp_duration(sources: Sources, requested: float | int | str | None, fallback: float) -> float:
    source_duration = duration_s(sources.camera)
    try:
        requested_duration = float(requested if requested is not None else fallback)
    except (TypeError, ValueError):
        requested_duration = fallback
    return max(1.0, min(requested_duration, source_duration))


def _intent_from_model_payload(parsed: dict, sources: Sources, fallback: EditIntent, receipts: Receipts) -> EditIntent:
    identity = str(parsed.get("identity") or fallback.identity).strip().lower()
    if identity not in SLUGS:
        receipts.log(
            "model_repair",
            field="identity",
            rejected=identity,
            selected=fallback.identity,
            reason="not_in_frozen_identity_pack",
        )
        identity = fallback.identity
    shorts_target = parsed.get("shorts_target", fallback.shorts_target)
    try:
        shorts_target_int = max(0, int(shorts_target))
    except (TypeError, ValueError):
        receipts.log("model_repair", field="shorts_target", rejected=str(shorts_target), selected=fallback.shorts_target)
        shorts_target_int = fallback.shorts_target
    return EditIntent(
        target_duration_s=_clamp_duration(sources, parsed.get("target_duration_s"), fallback.target_duration_s),
        identity=identity,
        shorts_target=shorts_target_int,
        hook=str(parsed.get("hook") or fallback.hook),
        title=str(parsed.get("title") or fallback.title),
    )


def create_intent(
    sources: Sources,
    run_dir: Path,
    receipts: Receipts,
    policy: RunPolicy,
    cost: CostTracker,
    *,
    target_duration_s: float | None = None,
) -> EditIntent:
    fallback = default_intent(sources, target_duration_s=target_duration_s)
    prompt = {
        "sources": sources.as_dict(),
        "target_duration_s": target_duration_s,
        "task": "Choose duration, identity, hook, title, and shorts target for a proof-gated YouTube edit.",
    }
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if policy.local_only:
        receipts.log("model_call", provider="openrouter", status="skipped", reason="local_only")
        (run_dir / "intent.json").write_text(json.dumps(fallback.as_dict(), indent=2), encoding="utf-8")
        return fallback
    if not api_key:
        receipts.log("model_call", provider="openrouter", status="skipped", reason="OPENROUTER_API_KEY missing")
        (run_dir / "intent.json").write_text(json.dumps(fallback.as_dict(), indent=2), encoding="utf-8")
        return fallback

    policy.require_cloud_allowed("openrouter", receipts)
    payload = json.dumps(
        {
            "model": os.environ.get("EDDY_V2_OPENROUTER_MODEL", "anthropic/claude-sonnet-5"),
            "messages": [
                {"role": "system", "content": "Return only compact JSON with target_duration_s, identity, shorts_target, hook, title."},
                {"role": "user", "content": json.dumps(prompt)},
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        cost.charge("openrouter_editor", 0.25, provider="openrouter")
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        intent = _intent_from_model_payload(parsed, sources, fallback, receipts)
        receipts.log("model_call", provider="openrouter", status="ok", response_id=data.get("id"))
    except Exception as exc:
        receipts.log("model_call", provider="openrouter", status="failed", error=str(exc))
        intent = fallback
    (run_dir / "intent.json").write_text(json.dumps(intent.as_dict(), indent=2), encoding="utf-8")
    return intent
