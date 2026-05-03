from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database import ensure_database, get_db_connection, json_dumps, row_to_dict
from .elevenlabs_client import create_timestamped_speech, fake_timestamped_speech
from .voice_config import (
    VoiceConfigurationError,
    get_voice_profile,
    get_voice_settings,
    redact_secrets,
)

MEDIA_ROOT = Path(os.environ.get("VOICE_MEDIA_ROOT", Path(__file__).with_name("media") / "voice"))
MEDIA_URL_PREFIX = "/media/voice"
ORDINARY_MAX_GAP_MS = 900


@dataclass(frozen=True)
class VoiceUtterance:
    line_index: int
    speaker_id: str
    speaker_label: str
    text: str
    gap_before_ms: int


def build_episode_voice(round_number: int = 7, phase: str = "tribal") -> dict[str, Any]:
    ensure_database()
    settings = get_voice_settings()
    if settings.provider == "disabled":
        return _voice_status(round_number, phase, provider=settings.provider)
    if settings.provider == "elevenlabs" and not settings.api_key:
        raise VoiceConfigurationError(
            "VOICE_PROVIDER=elevenlabs requires ELEVENLABS_API_KEY in the backend environment"
        )

    conn = get_db_connection()
    try:
        events = _episode_events(conn, round_number, phase)
        agents = _agent_labels(conn)
        for event in events:
            _build_event_voice(conn, event, agents, settings)
        conn.commit()
        return _voice_status(round_number, phase, provider=settings.provider, conn=conn)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_voice_status(round_number: int = 7, phase: str = "tribal") -> dict[str, Any]:
    ensure_database()
    settings = get_voice_settings()
    conn = get_db_connection()
    try:
        return _voice_status(round_number, phase, provider=settings.provider, conn=conn)
    finally:
        conn.close()


def attach_voice_timelines(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not events:
        return events
    conn = get_db_connection()
    try:
        event_ids = [event["id"] for event in events]
        placeholders = ",".join("?" for _ in event_ids)
        rows = conn.execute(
            f"""
            SELECT * FROM VoiceLines
            WHERE story_event_id IN ({placeholders})
            ORDER BY story_event_id, line_index
            """,
            event_ids,
        ).fetchall()
        by_event: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            line = _public_voice_line(row_to_dict(row))
            by_event.setdefault(line["story_event_id"], []).append(line)

        enriched = []
        for event in events:
            payload = dict(event.get("payload") or {})
            if event["id"] in by_event:
                payload["voice_timeline"] = by_event[event["id"]]
            enriched.append({**event, "payload": payload})
        return enriched
    finally:
        conn.close()


def _build_event_voice(conn, event: dict[str, Any], agents: dict[str, str], settings) -> None:
    utterances = extract_utterances(event, agents)
    current_ms = 0
    for utterance in utterances:
        start_ms = current_ms + utterance.gap_before_ms
        profile = get_voice_profile(utterance.speaker_id, utterance.speaker_label)
        text_hash = _text_hash(utterance.text)
        cache_key = _cache_key(profile.voice_id, settings.model_id, utterance.speaker_id, text_hash)
        existing = _existing_event_line(conn, event["id"], utterance.line_index)
        if existing and existing["status"] == "ready":
            current_ms = int(existing["end_ms"])
            continue

        reusable = _existing_cache_line(conn, cache_key)
        if reusable:
            duration_ms = int(reusable["duration_ms"])
            end_ms = start_ms + duration_ms
            _upsert_voice_line(
                conn,
                event=event,
                utterance=utterance,
                profile=profile,
                model_id=settings.model_id,
                text_hash=text_hash,
                cache_key=cache_key,
                audio_path=reusable["audio_path"],
                audio_url=reusable["audio_url"],
                duration_ms=duration_ms,
                start_ms=start_ms,
                end_ms=end_ms,
                alignment=reusable.get("alignment_json") or {},
                status="ready",
                error_message=None,
            )
            current_ms = end_ms
            continue

        try:
            speech = _generate_speech(utterance.text, profile, settings)
            audio_path, audio_url = _write_audio(event, utterance, text_hash, speech.audio_bytes, settings.provider)
            duration_ms = speech.duration_ms
            status = "ready"
            error_message = None
            alignment = speech.alignment
        except Exception as exc:
            duration_ms = max(900, len(utterance.text.split()) * 360)
            audio_path = None
            audio_url = None
            status = "failed"
            error_message = redact_secrets(exc)
            alignment = {}

        end_ms = start_ms + duration_ms
        _upsert_voice_line(
            conn,
            event=event,
            utterance=utterance,
            profile=profile,
            model_id=settings.model_id,
            text_hash=text_hash,
            cache_key=cache_key,
            audio_path=audio_path,
            audio_url=audio_url,
            duration_ms=duration_ms,
            start_ms=start_ms,
            end_ms=end_ms,
            alignment=alignment,
            status=status,
            error_message=error_message,
        )
        current_ms = end_ms

    if utterances:
        conn.execute(
            """
            UPDATE StoryEvents
            SET duration_ms = ?
            WHERE id = ?
            """,
            (current_ms + _visual_tail_ms(event), event["id"]),
        )


def extract_utterances(event: dict[str, Any], agents: dict[str, str]) -> list[VoiceUtterance]:
    utterances: list[VoiceUtterance] = []

    def add(speaker_id: str, text: str, gap: int) -> None:
        cleaned = " ".join(text.split())
        if not cleaned:
            return
        utterances.append(
            VoiceUtterance(
                line_index=len(utterances),
                speaker_id=speaker_id,
                speaker_label=_speaker_label(speaker_id, agents),
                text=cleaned,
                gap_before_ms=gap,
            )
        )

    kind = event["kind"]
    payload = event.get("payload") or {}
    host_narration = payload.get("host_narration")

    if kind == "host_question":
        add("host", event["dialogue"], 0)
        return utterances
    if kind == "vote_reveal":
        add("host", f"{event['title']}. {event['dialogue']}.", 600)
        return utterances
    if kind == "elimination":
        add("host", event["dialogue"], 900)
        return utterances
    if kind == "vote_booth":
        actor = _primary_non_host(event)
        add("host", f"{_speaker_label(actor, agents)} steps into the voting booth.", 0)
        add(actor, event["dialogue"], 450)
        return utterances

    if isinstance(host_narration, str):
        add("host", host_narration, 0)

    if kind == "conversation":
        for line in _speaker_lines(payload):
            add(line["agent_id"], line["text"], 300 if utterances else 0)
        return utterances

    actor = _primary_non_host(event)
    if actor:
        add(actor, event["dialogue"], 350 if utterances else 0)
    elif not utterances:
        add("host", event["dialogue"], 0)
    return utterances


def _generate_speech(text: str, profile, settings):
    if settings.provider == "fake":
        return fake_timestamped_speech(text)
    if settings.provider == "elevenlabs":
        return create_timestamped_speech(text=text, profile=profile, settings=settings)
    raise VoiceConfigurationError("Voice provider is disabled")


def _write_audio(
    event: dict[str, Any],
    utterance: VoiceUtterance,
    text_hash: str,
    audio_bytes: bytes,
    provider: str,
) -> tuple[str, str]:
    extension = "wav" if provider == "fake" else "mp3"
    directory = MEDIA_ROOT / str(event["round"])
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{event['id']}-{utterance.line_index}-{text_hash[:12]}.{extension}"
    path = directory / filename
    path.write_bytes(audio_bytes)
    return str(path), f"{MEDIA_URL_PREFIX}/{event['round']}/{filename}"


def _upsert_voice_line(
    conn,
    *,
    event: dict[str, Any],
    utterance: VoiceUtterance,
    profile,
    model_id: str,
    text_hash: str,
    cache_key: str,
    audio_path: str | None,
    audio_url: str | None,
    duration_ms: int,
    start_ms: int,
    end_ms: int,
    alignment: dict[str, Any],
    status: str,
    error_message: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO VoiceLines (
            story_event_id, round, event_sequence, line_index, speaker_id, speaker_label,
            voice_id, model_id, text, text_hash, cache_key, audio_path, audio_url,
            duration_ms, start_ms, end_ms, alignment_json, status, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(story_event_id, line_index) DO UPDATE SET
            speaker_id = excluded.speaker_id,
            speaker_label = excluded.speaker_label,
            voice_id = excluded.voice_id,
            model_id = excluded.model_id,
            text = excluded.text,
            text_hash = excluded.text_hash,
            cache_key = excluded.cache_key,
            audio_path = excluded.audio_path,
            audio_url = excluded.audio_url,
            duration_ms = excluded.duration_ms,
            start_ms = excluded.start_ms,
            end_ms = excluded.end_ms,
            alignment_json = excluded.alignment_json,
            status = excluded.status,
            error_message = excluded.error_message,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            event["id"],
            event["round"],
            event["sequence"],
            utterance.line_index,
            utterance.speaker_id,
            utterance.speaker_label,
            profile.voice_id,
            model_id,
            utterance.text,
            text_hash,
            cache_key,
            audio_path,
            audio_url,
            duration_ms,
            start_ms,
            end_ms,
            json_dumps(alignment),
            status,
            error_message,
        ),
    )


def _voice_status(
    round_number: int,
    phase: str,
    *,
    provider: str,
    conn=None,
) -> dict[str, Any]:
    close_conn = conn is None
    conn = conn or get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM VoiceLines
            WHERE round = ?
            GROUP BY status
            """,
            (round_number,),
        ).fetchall()
        events = _episode_events(conn, round_number, phase)
        total_lines = conn.execute(
            "SELECT COUNT(*) AS count FROM VoiceLines WHERE round = ?",
            (round_number,),
        ).fetchone()["count"]
        return {
            "provider": provider,
            "round": round_number,
            "phase": phase,
            "event_count": len(events),
            "line_count": total_lines,
            "statuses": {row["status"]: row["count"] for row in rows},
        }
    finally:
        if close_conn:
            conn.close()


def _public_voice_line(line: dict[str, Any]) -> dict[str, Any]:
    return {
        "story_event_id": line["story_event_id"],
        "line_index": line["line_index"],
        "speaker_id": line["speaker_id"],
        "speaker_label": line["speaker_label"],
        "text": line["text"],
        "audio_url": line["audio_url"],
        "duration_ms": line["duration_ms"],
        "start_ms": line["start_ms"],
        "end_ms": line["end_ms"],
        "status": line["status"],
    }


def _episode_events(conn, round_number: int, phase: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM StoryEvents
        WHERE round = ? AND phase = ?
        ORDER BY sequence
        """,
        (round_number, phase),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def _agent_labels(conn) -> dict[str, str]:
    rows = conn.execute("SELECT agent_id, pseudonym FROM Agents").fetchall()
    return {row["agent_id"]: row["pseudonym"] for row in rows} | {"host": "Host"}


def _speaker_label(speaker_id: str | None, agents: dict[str, str]) -> str:
    if not speaker_id:
        return "Host"
    return agents.get(speaker_id, speaker_id)


def _speaker_lines(payload: dict[str, Any]) -> list[dict[str, str]]:
    lines = payload.get("speaker_lines")
    if not isinstance(lines, list):
        return []
    valid = []
    for line in lines:
        if (
            isinstance(line, dict)
            and isinstance(line.get("agent_id"), str)
            and isinstance(line.get("text"), str)
        ):
            valid.append({"agent_id": line["agent_id"], "text": line["text"]})
    return valid


def _primary_non_host(event: dict[str, Any]) -> str:
    for actor_id in event.get("actor_ids") or []:
        if actor_id != "host":
            return actor_id
    return ""


def _existing_event_line(conn, story_event_id: int, line_index: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM VoiceLines WHERE story_event_id = ? AND line_index = ?",
        (story_event_id, line_index),
    ).fetchone()
    return row_to_dict(row)


def _existing_cache_line(conn, cache_key: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM VoiceLines
        WHERE cache_key = ? AND status = 'ready'
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (cache_key,),
    ).fetchone()
    return row_to_dict(row)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_key(voice_id: str, model_id: str, speaker_id: str, text_hash: str) -> str:
    return hashlib.sha256(f"{speaker_id}|{voice_id}|{model_id}|{text_hash}".encode("utf-8")).hexdigest()


def _visual_tail_ms(event: dict[str, Any]) -> int:
    if event["kind"] == "elimination":
        return 1200
    if event["kind"] == "vote_reveal":
        return 800
    return 500
