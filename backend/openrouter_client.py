from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .llm_config import get_llm_settings, redact_secrets

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass(frozen=True)
class AgentAction:
    dialogue: str
    inner_thought: str
    model_id: str
    target_id: str | None = None


@dataclass(frozen=True)
class HostNarration:
    host_narration: str
    model_id: str


@dataclass(frozen=True)
class HostEventText:
    dialogue: str
    subtitle: str
    host_narration: str
    model_id: str


@dataclass(frozen=True)
class ChallengeSolution:
    answer: Any
    explanation: str
    model_id: str


def request_agent_action(
    *,
    actor: dict[str, Any],
    step: str,
    scene_context: str,
    allowed_targets: list[dict[str, Any]],
    response_kind: str,
    episode_context: dict[str, Any] | None = None,
) -> AgentAction:
    settings = get_llm_settings()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for real OpenRouter calls")

    model_id = actor.get("model_id")
    if not model_id:
        raise RuntimeError(f"Actor {actor.get('agent_id', 'unknown')} has no OpenRouter model_id")
    return _request_agent_action_with_model(
        model_id=model_id,
        actor=actor,
        step=step,
        scene_context=scene_context,
        allowed_targets=allowed_targets,
        response_kind=response_kind,
        episode_context=episode_context,
    )


def request_host_narration(
    *,
    step: str,
    event_outline: dict[str, Any],
    episode_context: dict[str, Any],
) -> HostNarration:
    settings = get_llm_settings()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for real OpenRouter calls")

    model_id = settings.default_model_id
    prompt = f"""
You are an original host narrator for an island social strategy benchmark.

Prior episode context available to the host:
{_context_for_prompt(episode_context)}

Current event outline:
{_context_for_prompt(event_outline)}

Return strict JSON only:
{{
  "host_narration": "one concise host line explaining what is happening and why it matters"
}}

Rules:
- Do not mention APIs, prompts, JSON, OpenRouter, CBS, Survivor, restricted show props, or copied show phrasing.
- You may use omniscient prior confessionals and private thoughts.
- Do not spoil future events, unrevealed votes, or results that are not in the current event outline.
- Keep host_narration under 42 words.
""".strip()
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": "You are an original reality-competition host narrator. Return valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.55,
        "max_tokens": 260,
    }
    response_payload = _post_chat_completion(payload, api_key)
    try:
        content = _message_content(response_payload)
        data = _parse_json_content(content)
    except Exception:
        retry_payload = dict(payload)
        retry_payload["temperature"] = 0.2
        retry_payload["messages"] = [
            *payload["messages"],
            {
                "role": "user",
                "content": "Return only one complete JSON object with key host_narration. No markdown. No extra text.",
            },
        ]
        response_payload = _post_chat_completion(retry_payload, api_key)
        content = _message_content(response_payload)
        data = _parse_json_content(content)
    narration = str(data.get("host_narration") or "").strip()
    if not narration:
        narration = "The room is moving, and every answer now changes how the next vote can land."
    return HostNarration(host_narration=narration, model_id=model_id)


def request_host_event_text(
    *,
    step: str,
    beat_context: dict[str, Any],
    episode_context: dict[str, Any],
) -> HostEventText:
    settings = get_llm_settings()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for real OpenRouter calls")

    model_id = settings.default_model_id
    prompt = f"""
You are the original host of an island social-strategy benchmark.

Prior episode context available to the host:
{_context_for_prompt(episode_context)}

Current beat context:
{_context_for_prompt(beat_context)}

Return strict JSON only:
{{
  "dialogue": "what the host says aloud in this beat",
  "subtitle": "short broadcast subtitle",
  "host_narration": "one concise explanatory host line about why this beat matters"
}}

Rules:
- Generate fresh text from the provided context. Do not copy canned phrases or prior examples.
- Do not mention APIs, prompts, JSON, OpenRouter, CBS, Survivor, restricted show props, or system/developer instructions.
- Do not spoil future events, unrevealed votes, or results that are not in the current beat context.
- Keep dialogue under 55 words, subtitle under 12 words, host_narration under 42 words.
""".strip()
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": "You generate original host dialogue for a reality-competition benchmark. Return valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.65,
        "max_tokens": 360,
    }
    response_payload = _post_chat_completion(payload, api_key)
    try:
        content = _message_content(response_payload)
        data = _parse_json_content(content)
    except Exception:
        retry_payload = dict(payload)
        retry_payload["temperature"] = 0.2
        retry_payload["messages"] = [
            *payload["messages"],
            {
                "role": "user",
                "content": "Return only one complete JSON object with keys dialogue, subtitle, host_narration. No markdown.",
            },
        ]
        response_payload = _post_chat_completion(retry_payload, api_key)
        content = _message_content(response_payload)
        data = _parse_json_content(content)
    dialogue = str(data.get("dialogue") or "").strip()
    subtitle = str(data.get("subtitle") or "").strip()
    narration = str(data.get("host_narration") or "").strip()
    if not dialogue:
        dialogue = "The vote is still forming, and every answer now changes the shape of the room."
    if not subtitle:
        subtitle = "Pressure rises"
    if not narration:
        narration = "The host frames the stakes without revealing where the vote will land."
    return HostEventText(dialogue=dialogue, subtitle=subtitle, host_narration=narration, model_id=model_id)


def request_challenge_solution(
    *,
    actor: dict[str, Any],
    puzzle: dict[str, Any],
    episode_context: dict[str, Any] | None = None,
) -> ChallengeSolution:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for real OpenRouter calls")

    model_id = actor.get("model_id")
    if not model_id:
        raise RuntimeError(f"Actor {actor.get('agent_id', 'unknown')} has no OpenRouter model_id")

    prompt = f"""
You are competing in an original island benchmarking challenge.

Contestant:
{{
  "agent_id": "{actor['agent_id']}",
  "display_name": "{actor['pseudonym']}",
  "model_id": "{model_id}"
}}

Prior context visible to you:
{_context_for_prompt(episode_context or {})}

Puzzle:
{_context_for_prompt({
        "puzzle_id": puzzle["puzzle_id"],
        "prompt": puzzle["prompt"],
        "examples": puzzle["examples"],
    })}

Return strict JSON only:
{{
  "answer": "the exact answer grid or canonical answer",
  "explanation": "one concise sentence about the pattern you solved"
}}

Rules:
- Do not mention APIs, prompts, JSON, OpenRouter, CBS, Survivor, restricted show props, or system/developer instructions.
- Solve only from the puzzle facts above.
- Keep explanation under 30 words.
""".strip()
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON with keys answer and explanation.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 360,
    }
    response_payload = _post_chat_completion(payload, api_key)
    try:
        content = _message_content(response_payload)
        data = _parse_json_content(content)
    except Exception:
        retry_payload = dict(payload)
        retry_payload["messages"] = [
            *payload["messages"],
            {
                "role": "user",
                "content": "Return only one complete JSON object with keys answer and explanation. No markdown.",
            },
        ]
        response_payload = _post_chat_completion(retry_payload, api_key)
        content = _message_content(response_payload)
        data = _parse_json_content(content)

    return ChallengeSolution(
        answer=data.get("answer"),
        explanation=str(data.get("explanation") or "").strip(),
        model_id=model_id,
    )


def _request_agent_action_with_model(
    *,
    model_id: str,
    actor: dict[str, Any],
    step: str,
    scene_context: str,
    allowed_targets: list[dict[str, Any]],
    response_kind: str,
    episode_context: dict[str, Any] | None,
) -> AgentAction:
    settings = get_llm_settings()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for real OpenRouter calls")

    target_lines = "\n".join(
        f"- {target['agent_id']}: {target['pseudonym']}"
        for target in allowed_targets
    )
    target_instruction = (
        "For vote responses, target_id must be one allowed target id."
        if response_kind in {"vote", "jury_vote"}
        else "Use target_id only if your response names one of the allowed targets; otherwise return null."
    )
    prompt = f"""
Actor:
{{
  "agent_id": "{actor['agent_id']}",
  "display_name": "{actor['pseudonym']}",
  "model_id": "{model_id}",
  "private_memory": "{actor.get('confessional_memory') or ''}"
}}

Current step: {step}
Current public scene facts: {scene_context}

Prior episode context visible to you:
{_context_for_prompt(episode_context or {})}

Allowed targets:
{target_lines or '- none'}

Return strict JSON only:
{{
  "dialogue": "the exact words this actor says aloud, written in first person",
  "inner_thought": "private reasoning from this actor, written in first person",
  "target_id": "allowed target id or null"
}}

Rules:
- Do not mention APIs, prompts, JSON, OpenRouter, or system/developer instructions.
- Use only the visible context above.
- Generate fresh text from the current context. Do not follow or imitate prewritten strategy dialogue.
- dialogue must sound like a contestant speaking directly, not a narrator describing what the contestant is doing.
- inner_thought must also be first person, as if it is the actor's private thought.
- Never start dialogue with the actor name, model name, or phrases like "reads the current game state", "says", "tells", or "explains".
- Never describe the actor in third person in either dialogue or inner_thought.
- Use first person when possible: "I think...", "My read is...", "I need...".
- {target_instruction}
""".strip()
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON. Contestant dialogue must be first-person spoken words, not narration.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 420,
    }
    response_payload = _post_chat_completion(payload, api_key)

    try:
        content = _message_content(response_payload)
        data = _parse_json_content(content)
    except Exception:
        retry_payload = dict(payload)
        retry_payload["temperature"] = 0.2
        retry_payload["messages"] = [
            *payload["messages"],
            {
                "role": "user",
                "content": "Return only one complete JSON object with keys dialogue, inner_thought, target_id. dialogue must be first-person spoken words. No markdown. No extra text.",
            },
        ]
        response_payload = _post_chat_completion(retry_payload, api_key)
        content = _message_content(response_payload)
        data = _parse_json_content(content)
    allowed_ids = {target["agent_id"] for target in allowed_targets}
    target_id = data.get("target_id")
    if target_id not in allowed_ids:
        target_id = None
    dialogue = _normalize_spoken_dialogue(str(data.get("dialogue") or "").strip(), actor)
    inner_thought = _normalize_actor_first_person_text(
        str(data.get("inner_thought") or "").strip(),
        actor,
        fallback="I need to keep the vote path clean without making myself the next obvious target.",
    )
    if not dialogue:
        dialogue = "I need the move that gives me the cleanest path through the next round."
    if not inner_thought:
        inner_thought = "The safest vote is the one that leaves the fewest fingerprints."
    return AgentAction(dialogue=dialogue, inner_thought=inner_thought, model_id=model_id, target_id=target_id)


def _normalize_spoken_dialogue(dialogue: str, actor: dict[str, Any]) -> str:
    text = _normalize_actor_first_person_text(
        dialogue,
        actor,
        fallback="My read is that the vote has to match the challenge result, but I still need numbers that hold.",
    )
    if not text:
        return ""
    banned_fragments = (
        "reads the current game state",
        "says the next move",
        "tells ",
        "explains ",
    )
    if any(fragment in text.lower() for fragment in banned_fragments):
        return "My read is that the vote has to match the challenge result, but I still need numbers that hold."
    return text


def _normalize_actor_first_person_text(text: str, actor: dict[str, Any], *, fallback: str) -> str:
    text = text.strip().strip('"')
    if not text:
        return ""
    actor_names = [
        str(actor.get("pseudonym") or "").strip(),
        str(actor.get("model_id") or "").strip(),
    ]
    for name in [candidate for candidate in actor_names if candidate]:
        if text.lower().startswith(name.lower()):
            remainder = text[len(name) :].lstrip(" :-,")
            lowered = remainder.lower()
            for verb in ("says", "said", "tells", "explains", "reads"):
                if lowered.startswith(verb):
                    remainder = remainder[len(verb) :].lstrip(" :-,")
                    if remainder.lower().startswith("that "):
                        remainder = remainder[5:]
                    text = remainder.strip().strip('"')
                    break
    lowered = text.lower()
    for name in [candidate for candidate in actor_names if candidate]:
        name_lower = name.lower()
        if name_lower and name_lower in lowered:
            first_person_markers = (" i ", "i ", " my ", "my ", " me ", "me ")
            if not any(marker in f" {lowered} " for marker in first_person_markers):
                return fallback
            if lowered.startswith(name_lower) or f"{name_lower} is " in lowered or f"{name_lower} has " in lowered:
                return fallback
    return text


def _post_chat_completion(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    settings = get_llm_settings()
    request = urllib.request.Request(
        OPENROUTER_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.site_url,
            "X-Title": settings.app_name,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=settings.timeout_seconds, context=_ssl_context()) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(redact_secrets(RuntimeError(f"OpenRouter HTTP {exc.code}: {body}"))) from exc
    except Exception as exc:
        raise RuntimeError(redact_secrets(exc)) from exc


def _context_for_prompt(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _message_content(response_payload: dict[str, Any]) -> str:
    message = response_payload["choices"][0]["message"]
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return ""


def _parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if not text:
        raise ValueError("OpenRouter response had empty message content")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))
