from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal


VoiceProvider = Literal["disabled", "fake", "elevenlabs"]

SECRET_PATTERNS = [
    re.compile(r"sk_[A-Za-z0-9_\\-]{16,}"),
    re.compile(r"(?i)(elevenlabs_api_key|xi-api-key|authorization)['\"\\s:=]+[^\\s,'\"]+"),
]


@dataclass(frozen=True)
class VoiceSettings:
    provider: VoiceProvider
    api_key: str | None
    model_id: str
    output_format: str


@dataclass(frozen=True)
class VoiceProfile:
    speaker_id: str
    label: str
    voice_id: str
    stability: float
    similarity_boost: float


DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"

VOICE_REGISTRY: dict[str, VoiceProfile] = {
    "host": VoiceProfile("host", "Host", "21m00Tcm4TlvDq8ikWAM", 0.48, 0.76),
    "agent-alpha": VoiceProfile("agent-alpha", "GPT-4.1", "TxGEqnHWrfWFTfGW9XjX", 0.54, 0.72),
    "agent-bravo": VoiceProfile("agent-bravo", "Claude Sonnet 4.5", "ErXwobaYiN019PkySvjV", 0.58, 0.70),
    "agent-cipher": VoiceProfile("agent-cipher", "Gemini 2.5 Pro", "EXAVITQu4vr4xnSDxMaL", 0.55, 0.70),
    "agent-delta": VoiceProfile("agent-delta", "Grok 4.3", "pNInz6obpgDQGcFmaJgB", 0.42, 0.74),
    "agent-echo": VoiceProfile("agent-echo", "Llama 3.3 70B", "yoZ06aMxZJJ28mfd3POQ", 0.64, 0.68),
    "agent-flint": VoiceProfile("agent-flint", "Mistral Large", "VR6AewLTigWG4xSOukaG", 0.46, 0.72),
}


def get_voice_settings() -> VoiceSettings:
    provider = os.environ.get("VOICE_PROVIDER", "fake").strip().lower()
    if provider not in {"disabled", "fake", "elevenlabs"}:
        raise VoiceConfigurationError(
            "VOICE_PROVIDER must be one of disabled, fake, or elevenlabs"
        )
    return VoiceSettings(
        provider=provider,  # type: ignore[arg-type]
        api_key=os.environ.get("ELEVENLABS_API_KEY") or None,
        model_id=os.environ.get("VOICE_MODEL_ID", DEFAULT_MODEL_ID),
        output_format=os.environ.get("VOICE_OUTPUT_FORMAT", DEFAULT_OUTPUT_FORMAT),
    )


def require_elevenlabs_key(settings: VoiceSettings) -> str:
    if settings.provider != "elevenlabs":
        raise VoiceConfigurationError("ElevenLabs key is only required for the elevenlabs provider")
    if not settings.api_key:
        raise VoiceConfigurationError(
            "VOICE_PROVIDER=elevenlabs requires ELEVENLABS_API_KEY in the backend environment"
        )
    return settings.api_key


def get_voice_profile(speaker_id: str, fallback_label: str | None = None) -> VoiceProfile:
    if speaker_id in VOICE_REGISTRY:
        return VOICE_REGISTRY[speaker_id]
    return VoiceProfile(
        speaker_id=speaker_id,
        label=fallback_label or speaker_id,
        voice_id=VOICE_REGISTRY["host"].voice_id,
        stability=0.52,
        similarity_boost=0.70,
    )


def redact_secrets(value: object) -> str:
    text = str(value)
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if api_key:
        text = text.replace(api_key, "[REDACTED]")
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


class VoiceConfigurationError(RuntimeError):
    pass
