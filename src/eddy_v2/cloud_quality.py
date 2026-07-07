from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

DEFAULT_OPENROUTER_MODEL = "anthropic/claude-sonnet-5"


def _present(environ: Mapping[str, str], name: str) -> bool:
    return bool(environ.get(name))


def cloud_audio_profile(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    descript_ready = _present(env, "DESCRIPT_API_KEY")
    auphonic_key_ready = _present(env, "AUPHONIC_API_KEY")
    auphonic_preset_ready = _present(env, "AUPHONIC_PRESET") or _present(env, "AUPHONIC_PRESET_UUID")
    elevenlabs_ready = _present(env, "ELEVENLABS_API_KEY")

    providers = {
        "descript": {
            "configured": descript_ready,
            "missing": [] if descript_ready else ["DESCRIPT_API_KEY"],
            "unlocks": "strong_studio_sound",
            "uploads": "audio_extract_only",
        },
        "auphonic": {
            "configured": auphonic_key_ready and auphonic_preset_ready,
            "missing": (
                ([] if auphonic_key_ready else ["AUPHONIC_API_KEY"])
                + ([] if auphonic_preset_ready else ["AUPHONIC_PRESET_OR_AUPHONIC_PRESET_UUID"])
            ),
            "unlocks": "cloud_audio_fallback",
            "uploads": "audio_extract_only",
        },
        "elevenlabs": {
            "configured": elevenlabs_ready,
            "missing": [] if elevenlabs_ready else ["ELEVENLABS_API_KEY"],
            "unlocks": "cloud_audio_fallback",
            "uploads": "audio_extract_only",
        },
    }
    configured_providers = [provider for provider, profile in providers.items() if profile["configured"]]
    return {
        "audio_ready": bool(configured_providers),
        "strong_studio_sound_ready": providers["descript"]["configured"],
        "configured_providers": configured_providers,
        "providers": providers,
        "audio_quality_unblock_options": [
            {
                "provider": "descript",
                "required": ["DESCRIPT_API_KEY"],
                "unlocks": "strong_studio_sound",
                "uploads": "audio_extract_only",
            },
            {
                "provider": "auphonic",
                "required": ["AUPHONIC_API_KEY", "AUPHONIC_PRESET_OR_AUPHONIC_PRESET_UUID"],
                "unlocks": "cloud_audio_fallback",
                "uploads": "audio_extract_only",
            },
            {
                "provider": "elevenlabs",
                "required": ["ELEVENLABS_API_KEY"],
                "unlocks": "cloud_audio_fallback",
                "uploads": "audio_extract_only",
            },
        ],
        "strong_studio_sound_unblock": [] if descript_ready else ["DESCRIPT_API_KEY"],
    }


def cloud_model_profile(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    openrouter_ready = _present(env, "OPENROUTER_API_KEY")
    editor_model = env.get("EDDY_V2_OPENROUTER_EDITOR_MODEL") or env.get("EDDY_V2_OPENROUTER_MODEL") or DEFAULT_OPENROUTER_MODEL
    critic_model = env.get("EDDY_V2_OPENROUTER_CRITIC_MODEL") or editor_model
    return {
        "model_ready": openrouter_ready,
        "configured_providers": ["openrouter"] if openrouter_ready else [],
        "providers": {
            "openrouter": {
                "configured": openrouter_ready,
                "missing": [] if openrouter_ready else ["OPENROUTER_API_KEY"],
                "editor_model": editor_model,
                "critic_model": critic_model,
                "unlocks": "editor_critic_intent_loop",
                "fallback": "deterministic_default_intent",
            }
        },
        "model_unblock_options": [
            {
                "provider": "openrouter",
                "required": ["OPENROUTER_API_KEY"],
                "unlocks": "editor_critic_intent_loop",
                "fallback": "deterministic_default_intent",
            }
        ],
    }
