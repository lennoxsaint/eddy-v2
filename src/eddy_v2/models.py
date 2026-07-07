from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .commands import duration_s
from .cost import CostTracker
from .identities import SLUGS
from .policy import RunPolicy
from .receipts import Receipts
from .sources import Sources


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


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


def _dict_payload(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_from_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("model_json_not_object")
    return parsed


def _intent_from_model_payload(
    parsed: dict[str, Any],
    sources: Sources,
    fallback: EditIntent,
    receipts: Receipts,
    *,
    min_target_duration_s: float | None = None,
    min_shorts_target: int | None = None,
) -> EditIntent:
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
        if isinstance(shorts_target, bool):
            raise TypeError("bool is not a valid shorts target")
        shorts_target_int = max(0, int(shorts_target))
    except (TypeError, ValueError):
        receipts.log("model_repair", field="shorts_target", rejected=str(shorts_target), selected=fallback.shorts_target)
        shorts_target_int = fallback.shorts_target
    if min_shorts_target is not None and shorts_target_int < min_shorts_target:
        receipts.log(
            "model_repair",
            field="shorts_target",
            rejected=shorts_target_int,
            selected=min_shorts_target,
            reason="below_default_youtube_floor",
        )
        shorts_target_int = min_shorts_target
    duration = _clamp_duration(sources, parsed.get("target_duration_s"), fallback.target_duration_s)
    if min_target_duration_s is not None and duration < min_target_duration_s:
        receipts.log(
            "model_repair",
            field="target_duration_s",
            rejected=duration,
            selected=min_target_duration_s,
            reason="below_default_youtube_floor",
        )
        duration = min_target_duration_s
    return EditIntent(
        target_duration_s=duration,
        identity=identity,
        shorts_target=shorts_target_int,
        hook=str(parsed.get("hook") or fallback.hook),
        title=str(parsed.get("title") or fallback.title),
    )


def _call_openrouter_json(
    *,
    role: str,
    model: str,
    messages: list[dict[str, str]],
    api_key: str,
    receipts: Receipts,
) -> tuple[dict[str, Any], str | None]:
    fake_env = f"EDDY_V2_FAKE_OPENROUTER_{role.upper()}_JSON"
    fake_payload = os.environ.get(fake_env)
    if fake_payload:
        receipts.log("model_call", provider="openrouter", role=role, status="fake", model=model)
        return _json_from_text(fake_payload), f"fake-{role}"
    payload = json.dumps({"model": model, "messages": messages}).encode("utf-8")
    request = urllib.request.Request(
        OPENROUTER_URL,
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    receipts.log("model_call", provider="openrouter", role=role, status="ok", model=model, response_id=data.get("id"))
    return _json_from_text(content), data.get("id")


def _critic_prompt(editor_payload: dict[str, Any], prompt: dict[str, Any], fallback: EditIntent) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are Eddy V2's critic. Return only compact JSON with keys approved(boolean), "
                "issues(array of strings), and optional repair(object). Enforce: identity must be one of the frozen identity packs; "
                "target_duration_s must be feasible; shorts_target must be 0-5; hook/title must be specific and not generic. "
                "If not approved, include a repair object with valid target_duration_s, identity, shorts_target, hook, title."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({"input": prompt, "editor_payload": editor_payload, "fallback": fallback.as_dict()}),
        },
    ]


def _apply_critic(
    editor_payload: dict[str, Any],
    critic_payload: dict[str, Any],
    sources: Sources,
    fallback: EditIntent,
    receipts: Receipts,
    *,
    min_target_duration_s: float | None = None,
    min_shorts_target: int | None = None,
) -> EditIntent:
    approved = bool(critic_payload.get("approved"))
    issues = critic_payload.get("issues") if isinstance(critic_payload.get("issues"), list) else []
    receipts.log("model_critic", provider="openrouter", status="approved" if approved else "repaired", issues=issues)
    if approved:
        return _intent_from_model_payload(
            editor_payload,
            sources,
            fallback,
            receipts,
            min_target_duration_s=min_target_duration_s,
            min_shorts_target=min_shorts_target,
        )
    repair = _dict_payload(critic_payload.get("repair"))
    if repair:
        receipts.log("model_repair", field="intent", selected="critic_repair", reason="critic_not_approved")
        return _intent_from_model_payload(
            repair,
            sources,
            fallback,
            receipts,
            min_target_duration_s=min_target_duration_s,
            min_shorts_target=min_shorts_target,
        )
    receipts.log("model_repair", field="intent", selected="fallback", reason="critic_not_approved_without_repair")
    return fallback


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
    default_youtube_floor = target_duration_s is None
    prompt = {
        "sources": sources.as_dict(),
        "target_duration_s": target_duration_s,
        "default_target_duration_s": fallback.target_duration_s,
        "default_shorts_target": fallback.shorts_target,
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
    editor_model = os.environ.get("EDDY_V2_OPENROUTER_EDITOR_MODEL") or os.environ.get("EDDY_V2_OPENROUTER_MODEL", "anthropic/claude-sonnet-5")
    critic_model = os.environ.get("EDDY_V2_OPENROUTER_CRITIC_MODEL", editor_model)
    try:
        cost.charge("openrouter_editor", 0.25, provider="openrouter")
        editor_payload, editor_response_id = _call_openrouter_json(
            role="editor",
            model=editor_model,
            api_key=api_key,
            receipts=receipts,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Eddy V2's editor. Return only compact JSON with target_duration_s, identity, "
                        "shorts_target, hook, title. Prefer specific titles/hooks grounded in source metadata. "
                        "For the default autonomous YouTube edit, preserve the provided default duration floor "
                        "and produce at least the default Shorts target unless source duration makes that impossible. "
                        f"Identity must be one of: {', '.join(SLUGS)}."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt)},
            ],
        )
        cost.charge("openrouter_critic", 0.10, provider="openrouter")
        critic_payload, critic_response_id = _call_openrouter_json(
            role="critic",
            model=critic_model,
            api_key=api_key,
            receipts=receipts,
            messages=_critic_prompt(editor_payload, prompt, fallback),
        )
        receipts.log(
            "model_loop",
            provider="openrouter",
            status="complete",
            editor_response_id=editor_response_id,
            critic_response_id=critic_response_id,
        )
        intent = _apply_critic(
            editor_payload,
            critic_payload,
            sources,
            fallback,
            receipts,
            min_target_duration_s=fallback.target_duration_s if default_youtube_floor else None,
            min_shorts_target=fallback.shorts_target if default_youtube_floor else None,
        )
    except Exception as exc:
        receipts.log("model_loop", provider="openrouter", status="failed", error=str(exc))
        intent = fallback
    (run_dir / "intent.json").write_text(json.dumps(intent.as_dict(), indent=2), encoding="utf-8")
    return intent
