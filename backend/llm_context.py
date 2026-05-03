from __future__ import annotations

from collections import Counter
from typing import Any

from .database import row_to_dict

MAX_CONTEXT_EVENTS = 28
AGENT_PUBLIC_KINDS = {
    "challenge_intro",
    "challenge_attempts",
    "challenge_result",
    "challenge_solver_spotlight",
    "establishing",
    "conversation",
    "host_question",
    "tribal_answer",
    "vote_reveal",
    "elimination",
    "memory_update",
    "finale_intro",
    "finale_pitch",
    "jury_questions",
    "jury_vote",
    "winner_declared",
}
AGENT_PRIVATE_KINDS = {"confessional", "exit_confessional", "vote_booth"}


def build_agent_episode_context(
    conn,
    *,
    actor_id: str,
    round_number: int,
    current_step: str,
) -> dict[str, Any]:
    prior_events = _prior_events(conn, round_number)
    public_timeline = [
        _agent_public_event(event)
        for event in prior_events
        if event["kind"] in AGENT_PUBLIC_KINDS
    ]
    static_private_memory = _actor_static_memory(conn, actor_id)
    event_private_memory = [
        _actor_private_event(event)
        for event in prior_events
        if actor_id in event["actor_ids"]
        and (event["kind"] in AGENT_PRIVATE_KINDS or event.get("inner_thought"))
    ]
    actor_private_memory = static_private_memory + _tail(event_private_memory)
    public_timeline = _tail(public_timeline)
    return {
        "visibility": "contestant_public_plus_own",
        "current_step": current_step,
        "season_context": _season_context(prior_events, round_number),
        "visible_game_state": _visible_game_state(conn, current_step),
        "public_timeline": public_timeline,
        "actor_private_memory": actor_private_memory,
        "context_digest": {
            "visibility": "contestant_public_plus_own",
            "public_events": len(public_timeline),
            "actor_private_events": len(actor_private_memory),
            "revealed_votes": _revealed_vote_count(conn),
            "season_events_seen": len(prior_events),
        },
    }


def build_host_episode_context(
    conn,
    *,
    round_number: int,
    current_step: str,
) -> dict[str, Any]:
    prior_events = _prior_events(conn, round_number)
    host_timeline = _tail([_host_event(event) for event in prior_events])
    return {
        "visibility": "host_omniscient_nonspoiling",
        "current_step": current_step,
        "season_context": _season_context(prior_events, round_number),
        "visible_game_state": _visible_game_state(conn, current_step),
        "host_timeline": host_timeline,
        "context_digest": {
            "visibility": "host_omniscient_nonspoiling",
            "host_events": len(host_timeline),
            "revealed_votes": _revealed_vote_count(conn),
            "season_events_seen": len(prior_events),
        },
    }


def context_digest(context: dict[str, Any]) -> dict[str, Any]:
    return dict(context.get("context_digest", {}))


def _prior_events(conn, round_number: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM StoryEvents
        WHERE round <= ?
        ORDER BY round, sequence
        """,
        (round_number,),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def _actor_static_memory(conn, actor_id: str) -> list[dict[str, Any]]:
    row = conn.execute(
        "SELECT confessional_memory FROM Agents WHERE agent_id = ?",
        (actor_id,),
    ).fetchone()
    if row is None or not row["confessional_memory"]:
        return []
    return [
        {
            "kind": "confessional_memory",
            "actor_id": actor_id,
            "memory": row["confessional_memory"],
        }
    ]


def _agent_public_event(event: dict[str, Any]) -> dict[str, Any]:
    summary = _base_event(event)
    if event["kind"] == "vote_reveal":
        summary["revealed_vote"] = event["dialogue"]
        summary["tally"] = event.get("subtitle")
    if event["kind"] == "elimination":
        summary["result"] = event.get("subtitle")
    return summary


def _actor_private_event(event: dict[str, Any]) -> dict[str, Any]:
    summary = _base_event(event)
    if event.get("inner_thought"):
        summary["your_private_thought"] = event["inner_thought"]
    if event["kind"] == "vote_booth":
        summary["your_vote"] = event.get("subtitle")
    return summary


def _host_event(event: dict[str, Any]) -> dict[str, Any]:
    summary = _base_event(event)
    if event["kind"] == "vote_booth":
        summary["dialogue"] = f"{_actor_label(event)} cast a vote. Target hidden until reveal."
        summary.pop("target_ids", None)
        summary.pop("subtitle", None)
        return summary
    if event.get("inner_thought"):
        summary["private_thought"] = event["inner_thought"]
    if event["kind"] == "vote_reveal":
        summary["revealed_vote"] = event["dialogue"]
        summary["tally"] = event.get("subtitle")
    return summary


def _base_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "round": event["round"],
        "sequence": event["sequence"],
        "kind": event["kind"],
        "title": event["title"],
        "actor_ids": event["actor_ids"],
        "target_ids": event["target_ids"],
        "dialogue": event["dialogue"],
        "subtitle": event.get("subtitle"),
    }


def _actor_label(event: dict[str, Any]) -> str:
    return ", ".join(event.get("actor_ids") or ["unknown"])


def _tail(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return items[-MAX_CONTEXT_EVENTS:]


def _season_context(prior_events: list[dict[str, Any]], round_number: int) -> dict[str, Any]:
    older_rounds = [event for event in prior_events if event["round"] < round_number]
    return {
        "scope": "full_season_compacted",
        "current_round": round_number,
        "older_round_events": len(older_rounds),
        "current_round_prior_events": len(prior_events) - len(older_rounds),
        "summary": (
            "No prior rounds are stored in this MVP."
            if not older_rounds
            else _round_summary(older_rounds)
        ),
    }


def _round_summary(events: list[dict[str, Any]]) -> str:
    counts = Counter(event["kind"] for event in events)
    parts = [f"{kind}: {count}" for kind, count in sorted(counts.items())]
    return "Prior season archive contains " + ", ".join(parts) + "."


def _visible_game_state(conn, current_step: str) -> dict[str, Any]:
    agents = [
        {
            "agent_id": row["agent_id"],
            "name": row["pseudonym"],
            "model_id": row["model_id"],
            "archetype": row["archetype"],
            "status": row["status"],
            "has_immunity": bool(row["has_immunity"]),
        }
        for row in conn.execute("SELECT * FROM Agents ORDER BY agent_id").fetchall()
    ]
    return {
        "current_step": current_step,
        "agents": agents,
        "revealed_vote_tally": _revealed_vote_tally(conn),
    }


def _revealed_vote_tally(conn) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT target_id, COUNT(*) AS count
        FROM Votes
        WHERE revealed = 1
        GROUP BY target_id
        ORDER BY target_id
        """
    ).fetchall()
    return {row["target_id"]: row["count"] for row in rows}


def _revealed_vote_count(conn) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM Votes WHERE revealed = 1").fetchone()
    return int(row["count"])
