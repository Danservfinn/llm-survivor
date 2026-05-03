from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .voice_config import VoiceConfigurationError, VoiceProfile, VoiceSettings, redact_secrets, require_elevenlabs_key


@dataclass(frozen=True)
class SpeechResult:
    audio_bytes: bytes
    duration_ms: int
    alignment: dict[str, Any]


def create_timestamped_speech(
    *,
    text: str,
    profile: VoiceProfile,
    settings: VoiceSettings,
    timeout_seconds: int = 45,
) -> SpeechResult:
    api_key = require_elevenlabs_key(settings)
    endpoint = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{profile.voice_id}/with-timestamps"
        f"?output_format={settings.output_format}"
    )
    body = json.dumps(
        {
            "text": text,
            "model_id": settings.model_id,
            "voice_settings": {
                "stability": profile.stability,
                "similarity_boost": profile.similarity_boost,
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "xi-api-key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VoiceConfigurationError(
            f"ElevenLabs speech request failed with HTTP {exc.code}: {redact_secrets(detail)}"
        ) from exc
    except Exception as exc:
        raise VoiceConfigurationError(f"ElevenLabs speech request failed: {redact_secrets(exc)}") from exc

    encoded_audio = payload.get("audio_base64")
    if not isinstance(encoded_audio, str) or not encoded_audio:
        raise VoiceConfigurationError("ElevenLabs response did not include audio_base64")
    try:
        audio_bytes = base64.b64decode(encoded_audio)
    except Exception as exc:
        raise VoiceConfigurationError("ElevenLabs response included invalid audio_base64") from exc

    alignment = payload.get("alignment")
    if not isinstance(alignment, dict):
        alignment = {}
    duration_ms = _duration_from_alignment(alignment)
    if duration_ms <= 0:
        duration_ms = _estimate_duration_ms(text)
    return SpeechResult(audio_bytes=audio_bytes, duration_ms=duration_ms, alignment=alignment)


def fake_timestamped_speech(text: str) -> SpeechResult:
    duration_ms = _estimate_duration_ms(text)
    return SpeechResult(
        audio_bytes=_silent_wav_bytes(),
        duration_ms=duration_ms,
        alignment={
            "provider": "fake",
            "estimated_duration_ms": duration_ms,
        },
    )


def _duration_from_alignment(alignment: dict[str, Any]) -> int:
    ends = alignment.get("character_end_times_seconds")
    if not isinstance(ends, list) or not ends:
        return 0
    numeric_ends = [value for value in ends if isinstance(value, (int, float))]
    if not numeric_ends:
        return 0
    return int(max(numeric_ends) * 1000)


def _estimate_duration_ms(text: str) -> int:
    words = max(1, len(text.split()))
    return max(900, min(14000, words * 360))


def _silent_wav_bytes() -> bytes:
    # Valid short WAV fixture; timeline duration is carried separately.
    return (
        b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        b"@\x1f\x00\x00@\x1f\x00\x00\x01\x00\x08\x00data\x00\x00\x00\x00"
    )
