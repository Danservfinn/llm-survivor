from __future__ import annotations

import os
from dataclasses import dataclass


PROVIDER_OPENROUTER = "openrouter"


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    openrouter_configured: bool
    default_model_id: str
    timeout_seconds: float
    site_url: str
    app_name: str


def get_llm_settings() -> LLMSettings:
    return LLMSettings(
        provider=PROVIDER_OPENROUTER,
        openrouter_configured=bool(os.environ.get("OPENROUTER_API_KEY")),
        default_model_id=os.environ.get("OPENROUTER_DEFAULT_MODEL", "openai/gpt-4.1-mini"),
        timeout_seconds=float(os.environ.get("OPENROUTER_TIMEOUT_SECONDS", "45")),
        site_url=os.environ.get("OPENROUTER_SITE_URL", "http://localhost:3001"),
        app_name=os.environ.get("OPENROUTER_APP_NAME", "LLM Survivor Local"),
    )


def should_use_openrouter() -> bool:
    settings = get_llm_settings()
    return settings.openrouter_configured


def redact_secrets(exc: BaseException) -> str:
    message = str(exc)
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key:
        message = message.replace(api_key, "[redacted]")
    return message
