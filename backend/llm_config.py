from __future__ import annotations

import os
import json
import urllib.error
import urllib.request
from dataclasses import dataclass


PROVIDER_OPENROUTER = "openrouter"
PROVIDER_OLLAMA = "ollama"
PROVIDER_DETERMINISTIC = "deterministic"
SUPPORTED_PROVIDERS = {PROVIDER_OPENROUTER, PROVIDER_OLLAMA, PROVIDER_DETERMINISTIC}


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    openrouter_configured: bool
    ollama_configured: bool
    default_model_id: str
    timeout_seconds: float
    site_url: str
    app_name: str
    ollama_base_url: str
    ollama_host_model_id: str
    ollama_keep_alive: str
    ollama_num_ctx: int
    ollama_timeout_seconds: float
    ollama_available_models: list[str]
    ollama_required_models: list[str]
    ollama_missing_models: list[str]


def get_llm_settings() -> LLMSettings:
    provider = os.environ.get("LLM_PROVIDER", PROVIDER_OPENROUTER).strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        provider = PROVIDER_OPENROUTER
    ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    ollama_host_model_id = os.environ.get("OLLAMA_HOST_MODEL", "qwen2.5:1.5b")
    ollama_available_models = _available_ollama_models(ollama_base_url)
    ollama_required_models = _required_ollama_models(ollama_host_model_id)
    ollama_missing_models = [
        model_id for model_id in ollama_required_models if model_id not in ollama_available_models
    ]
    return LLMSettings(
        provider=provider,
        openrouter_configured=bool(os.environ.get("OPENROUTER_API_KEY")),
        ollama_configured=bool(ollama_base_url) and not ollama_missing_models,
        default_model_id=os.environ.get("OPENROUTER_DEFAULT_MODEL", "openai/gpt-4.1-mini"),
        timeout_seconds=float(os.environ.get("OPENROUTER_TIMEOUT_SECONDS", "45")),
        site_url=os.environ.get("OPENROUTER_SITE_URL", "http://localhost:3001"),
        app_name=os.environ.get("OPENROUTER_APP_NAME", "LLM Survivor Local"),
        ollama_base_url=ollama_base_url,
        ollama_host_model_id=ollama_host_model_id,
        ollama_keep_alive=os.environ.get("OLLAMA_KEEP_ALIVE_PER_CALL", "0"),
        ollama_num_ctx=int(os.environ.get("OLLAMA_NUM_CTX", "8192")),
        ollama_timeout_seconds=float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180")),
        ollama_available_models=ollama_available_models,
        ollama_required_models=ollama_required_models,
        ollama_missing_models=ollama_missing_models,
    )


def should_use_openrouter() -> bool:
    settings = get_llm_settings()
    return settings.provider == PROVIDER_OPENROUTER and settings.openrouter_configured


def should_use_ollama() -> bool:
    settings = get_llm_settings()
    return settings.provider == PROVIDER_OLLAMA and settings.ollama_configured


def should_use_live_llm() -> bool:
    return should_use_openrouter() or should_use_ollama()


def live_llm_provider() -> str:
    settings = get_llm_settings()
    if settings.provider == PROVIDER_OLLAMA and settings.ollama_configured:
        return PROVIDER_OLLAMA
    if settings.provider == PROVIDER_OPENROUTER and settings.openrouter_configured:
        return PROVIDER_OPENROUTER
    return PROVIDER_DETERMINISTIC


def failed_llm_provider() -> str:
    provider = live_llm_provider()
    if provider == PROVIDER_DETERMINISTIC:
        return PROVIDER_DETERMINISTIC
    return f"{provider}_failed"


def redact_secrets(exc: BaseException) -> str:
    message = str(exc)
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key:
        message = message.replace(api_key, "[redacted]")
    return message


def _required_ollama_models(host_model_id: str) -> list[str]:
    try:
        from .model_rosters import LOCAL_OLLAMA_MODELS
    except Exception:
        LOCAL_OLLAMA_MODELS = []
    model_ids = [host_model_id, *(model["model_id"] for model in LOCAL_OLLAMA_MODELS)]
    return sorted({model_id for model_id in model_ids if model_id})


def _available_ollama_models(base_url: str) -> list[str]:
    if not base_url:
        return []
    request = urllib.request.Request(f"{base_url}/api/tags", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return []
    return sorted(
        model["name"]
        for model in payload.get("models", [])
        if isinstance(model, dict) and isinstance(model.get("name"), str)
    )
