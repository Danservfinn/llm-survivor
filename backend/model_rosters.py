from __future__ import annotations

from copy import deepcopy
from typing import Any

from .fixtures import DEMO_AGENTS


CHEAP_RECENT_OPENROUTER_MODELS = [
    {
        "model_id": "ibm-granite/granite-4.1-8b",
        "display_name": "Granite 4.1 8B",
        "status": "cheap_recent",
    },
    {
        "model_id": "deepseek/deepseek-v4-flash",
        "display_name": "DeepSeek V4 Flash",
        "status": "cheap_recent",
    },
    {
        "model_id": "inclusionai/ling-2.6-flash",
        "display_name": "Ling 2.6 Flash",
        "status": "cheap_recent",
    },
    {
        "model_id": "google/gemma-4-26b-a4b-it",
        "display_name": "Gemma 4 26B A4B",
        "status": "cheap_recent",
    },
    {
        "model_id": "google/gemma-4-31b-it",
        "display_name": "Gemma 4 31B",
        "status": "cheap_recent",
    },
    {
        "model_id": "rekaai/reka-edge",
        "display_name": "Reka Edge",
        "status": "cheap_recent",
    },
    {
        "model_id": "qwen/qwen3.5-9b",
        "display_name": "Qwen3.5 9B",
        "status": "cheap_recent",
    },
    {
        "model_id": "openrouter/owl-alpha",
        "display_name": "Owl Alpha",
        "status": "free_test",
    },
    {
        "model_id": "inclusionai/ling-2.6-1t:free",
        "display_name": "Ling 2.6 1T Free",
        "status": "free_test",
    },
    {
        "model_id": "google/gemma-4-26b-a4b-it:free",
        "display_name": "Gemma 4 26B A4B Free",
        "status": "free_test",
    },
    {
        "model_id": "nvidia/nemotron-3-super-120b-a12b:free",
        "display_name": "Nemotron 3 Super 120B Free",
        "status": "free_test",
    },
]


FREE_OPENROUTER_MODELS = [
    model for model in CHEAP_RECENT_OPENROUTER_MODELS if model["status"] == "free_test"
]


def list_model_rosters() -> list[dict[str, Any]]:
    return [
        {
            "id": "default",
            "name": "Default Benchmark Models",
            "models": [
                {
                    "model_id": agent["model_id"],
                    "display_name": agent["pseudonym"],
                    "status": "default",
                }
                for agent in DEMO_AGENTS
            ],
        },
        {
            "id": "cheap_recent_openrouter",
            "name": "Cheap Recent OpenRouter",
            "models": CHEAP_RECENT_OPENROUTER_MODELS,
        },
        {
            "id": "all_free_openrouter",
            "name": "All Free OpenRouter Models",
            "models": FREE_OPENROUTER_MODELS,
        },
    ]


def agents_for_roster(roster_preset: str | None = None) -> list[dict[str, Any]]:
    if roster_preset == "cheap_recent_openrouter":
        return _agents_for_models(CHEAP_RECENT_OPENROUTER_MODELS)
    if roster_preset == "all_free_openrouter":
        return _agents_for_models(FREE_OPENROUTER_MODELS)
    return deepcopy(DEMO_AGENTS)


def _agents_for_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not models:
        return deepcopy(DEMO_AGENTS)

    base_agents = deepcopy(DEMO_AGENTS)
    roster_agents = base_agents[: len(models)]
    for agent, model in zip(roster_agents, models):
        agent["pseudonym"] = model["display_name"]
        agent["model_id"] = model["model_id"]
        agent["archetype"] = _archetype_for_model(model["display_name"])
        agent["confessional_memory"] = (
            f"{model['display_name']} is testing whether this model can survive a social-strategy benchmark."
        )
        agent["portrait_seed"] = model["model_id"].replace("/", "-").replace(":", "-")
    return roster_agents


def _archetype_for_model(display_name: str) -> str:
    if "Flash" in display_name:
        return "fast tactician"
    if "Gemma" in display_name:
        return "pattern generalist"
    if "Granite" in display_name:
        return "structured analyst"
    if "Reka" in display_name:
        return "adaptive wildcard"
    return "budget contender"
