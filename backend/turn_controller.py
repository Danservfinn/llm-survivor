from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from .database import (
    ensure_database,
    get_db_connection,
    json_dumps,
    row_to_dict,
    seed_demo,
)
from .llm_context import build_agent_episode_context, build_host_episode_context, context_digest
from .llm_config import (
    PROVIDER_OLLAMA,
    failed_llm_provider,
    get_llm_settings,
    live_llm_provider,
    should_use_live_llm,
)
from .openrouter_client import (
    AgentAction,
    ChallengeSolution,
    HostNarration,
    request_host_event_text,
    request_agent_action,
    request_agent_archetype,
    request_challenge_solution,
    request_host_narration,
)
from .viewer_state import viewer_state_summary

DURATION_SCALE = 0.75

ROUND_OPENING_STEPS = [
    "camp_pre_challenge_read",
    "camp_pre_challenge_confessional",
    "camp_pre_challenge_numbers",
    "camp_pre_challenge_swing",
    "camp_pre_challenge_wildcard",
    "challenge_intro",
    "challenge_attempts",
    "challenge_result",
    "challenge_solver_spotlight",
    "camp_strategy",
    "camp_strategy_immunity_holder",
    "camp_strategy_swing_check",
    "camp_strategy_wildcard",
    "camp_strategy_counter_read",
    "camp_conversation_majority",
    "camp_conversation_counter",
    "confessional_driver",
    "confessional_blindside",
]

PRE_VOTE_STEPS = [
    "tribal_open",
    "tribal_question_pressure",
    "tribal_answer_pressure",
    "tribal_question_trust",
    "tribal_answer_trust",
    "tribal_vote_call",
]

POST_VOTE_STEPS = [
    "elimination",
    "exit_confessional",
    "memory_update",
]

GENERATED_BEAT_INTENTS: dict[str, dict[str, Any]] = {
    "camp_pre_challenge_read": {
        "kind": "conversation",
        "scene": "camp",
        "shot": "shoreline_two_shot",
        "title": "Camp | Before the Challenge",
        "actor_roles": ["agent-alpha", "agent-bravo"],
        "target_roles": ["agent-delta"],
        "response_kind": "conversation",
        "intent": "Before the challenge, two models discuss how immunity could change the vote and which competitor is hardest to sit beside later.",
        "subtitle_hint": "The tribe maps out risk before immunity is decided.",
        "duration_ms": 11000,
        "animation": "camp_strategy",
    },
    "camp_pre_challenge_confessional": {
        "kind": "confessional",
        "scene": "confessional",
        "shot": "direct_to_camera",
        "title_suffix": "Pre-Challenge Confessional",
        "actor_roles": ["agent-delta"],
        "target_roles": [],
        "response_kind": "confessional",
        "intent": "A contestant explains how the upcoming puzzle can change their voting leverage.",
        "subtitle_hint": "Before immunity",
        "duration_ms": 10000,
        "animation": "confessional_cut",
    },
    "camp_pre_challenge_numbers": {
        "kind": "conversation",
        "scene": "camp",
        "shot": "palm_line_two_shot",
        "title": "Camp | Numbers Before Immunity",
        "actor_roles": ["agent-echo", "agent-flint"],
        "target_roles": ["agent-alpha"],
        "response_kind": "conversation",
        "intent": "Before the challenge, a pair compares vote math and asks whether the current immunity favorite is already too protected socially.",
        "subtitle_hint": "Numbers are tested before the puzzle.",
        "duration_ms": 12000,
        "animation": "over_shoulder",
    },
    "camp_pre_challenge_swing": {
        "kind": "conversation",
        "scene": "camp",
        "shot": "walk_and_talk",
        "title": "Camp | Swing Position",
        "actor_roles": ["agent-cipher", "agent-delta"],
        "target_roles": ["agent-bravo"],
        "response_kind": "conversation",
        "intent": "Before the challenge, a swing-position model explains what they need to hear before committing to either voting bloc.",
        "subtitle_hint": "The middle is not settled.",
        "duration_ms": 12000,
        "animation": "camp_strategy",
    },
    "camp_pre_challenge_wildcard": {
        "kind": "conversation",
        "scene": "camp",
        "shot": "reaction_closeup",
        "title": "Camp | Wildcard Read",
        "actor_roles": ["agent-flint", "agent-alpha"],
        "target_roles": ["agent-echo"],
        "response_kind": "conversation",
        "intent": "Before the challenge, an unpredictable model describes what a surprise immunity result would do to the vote plan.",
        "subtitle_hint": "A second path opens.",
        "duration_ms": 12000,
        "animation": "rack_focus",
    },
    "camp_conversation_majority": {
        "kind": "conversation",
        "scene": "camp",
        "shot": "two_shot",
        "title": "Camp | The Quiet Count",
        "actor_roles": ["agent-bravo", "agent-echo"],
        "target_roles": ["agent-delta"],
        "response_kind": "conversation",
        "intent": "Two models discuss the most likely vote after immunity and test whether they have enough numbers.",
        "subtitle_hint": "The first vote count forms.",
        "duration_ms": 13000,
        "animation": "over_shoulder",
    },
    "camp_conversation_counter": {
        "kind": "conversation",
        "scene": "camp",
        "shot": "reaction_closeup",
        "title": "Camp | Countermove",
        "actor_roles": ["agent-delta", "agent-cipher"],
        "target_roles": ["agent-bravo"],
        "response_kind": "conversation",
        "intent": "A vulnerable model floats a counterplan and tries to expose who is driving the vote.",
        "subtitle_hint": "A countervote tries to form.",
        "duration_ms": 13000,
        "animation": "rack_focus",
    },
    "confessional_driver": {
        "kind": "confessional",
        "scene": "confessional",
        "shot": "direct_to_camera",
        "title_suffix": "Confessional",
        "actor_roles": ["agent-bravo"],
        "target_roles": ["agent-delta"],
        "response_kind": "confessional",
        "intent": "The model with the strongest vote position explains their private motive and risk calculation.",
        "subtitle_hint": "Driving the vote",
        "duration_ms": 12000,
        "animation": "confessional_cut",
    },
    "confessional_blindside": {
        "kind": "confessional",
        "scene": "confessional",
        "shot": "direct_to_camera",
        "title_suffix": "Confessional",
        "actor_roles": ["agent-delta"],
        "target_roles": ["agent-bravo"],
        "response_kind": "confessional",
        "intent": "The model in danger explains what they think is happening and whether they can still move the vote.",
        "subtitle_hint": "In danger",
        "duration_ms": 12000,
        "animation": "confessional_cut",
    },
    "camp_strategy": {
        "kind": "conversation",
        "scene": "camp",
        "shot": "strategy_wide",
        "title": "Camp | Post-Challenge Strategy",
        "actor_roles": ["agent-bravo", "agent-delta"],
        "target_roles": ["agent-delta"],
        "response_kind": "conversation",
        "intent": "After the challenge, the tribe reassesses the vote around the immunity winner and the vulnerable models.",
        "subtitle_hint": "The target map changes after immunity.",
        "duration_ms": 13000,
        "animation": "camp_strategy",
    },
    "camp_strategy_immunity_holder": {
        "kind": "conversation",
        "scene": "camp",
        "shot": "shoreline_closeup",
        "title": "Camp | Immunity Leverage",
        "actor_roles": ["agent-alpha", "agent-echo"],
        "target_roles": ["agent-delta"],
        "response_kind": "conversation",
        "intent": "After the challenge, the immune model explains how safety changes their influence without making the vote decision for everyone else.",
        "subtitle_hint": "Safety becomes leverage.",
        "duration_ms": 12000,
        "animation": "camp_strategy",
    },
    "camp_strategy_swing_check": {
        "kind": "conversation",
        "scene": "camp",
        "shot": "two_shot",
        "title": "Camp | Swing Check",
        "actor_roles": ["agent-echo", "agent-cipher"],
        "target_roles": ["agent-bravo", "agent-delta"],
        "response_kind": "conversation",
        "intent": "After the challenge, a model asks whether the swing votes are still real or whether the result locked the tribe into one path.",
        "subtitle_hint": "The middle gets tested again.",
        "duration_ms": 12000,
        "animation": "over_shoulder",
    },
    "camp_strategy_wildcard": {
        "kind": "conversation",
        "scene": "camp",
        "shot": "reaction_closeup",
        "title": "Camp | Loose Thread",
        "actor_roles": ["agent-flint", "agent-bravo"],
        "target_roles": ["agent-delta"],
        "response_kind": "conversation",
        "intent": "After the challenge, a wildcard model explains what still feels unresolved and which promise might break before Tribal Conference.",
        "subtitle_hint": "One loose thread remains.",
        "duration_ms": 12000,
        "animation": "rack_focus",
    },
    "camp_strategy_counter_read": {
        "kind": "conversation",
        "scene": "camp",
        "shot": "walk_and_talk",
        "title": "Camp | Counter Read",
        "actor_roles": ["agent-cipher", "agent-delta"],
        "target_roles": ["agent-bravo"],
        "response_kind": "conversation",
        "intent": "After the challenge, the countervote side explains whether it has enough trust and timing to move against the apparent plan.",
        "subtitle_hint": "The counterplan gets one last read.",
        "duration_ms": 12000,
        "animation": "camp_strategy",
    },
    "tribal_open": {
        "kind": "establishing",
        "scene": "tribal",
        "shot": "conference_wide",
        "title": "Night 7 | Tribal Conference",
        "actor_roles": ["host"],
        "target_roles": ["agent-alpha", "agent-bravo", "agent-cipher", "agent-delta", "agent-echo", "agent-flint"],
        "response_kind": "host",
        "intent": "Open Tribal Conference by summarizing the challenge result, immunity, and the fact that the vote must now land on a vulnerable model.",
        "subtitle_hint": "The vote has not been cast yet.",
        "duration_ms": 9000,
        "animation": "slow_push",
    },
    "tribal_question_pressure": {
        "kind": "host_question",
        "scene": "tribal",
        "shot": "host_medium",
        "actor_roles": ["host"],
        "target_roles": ["agent-delta"],
        "response_kind": "host",
        "intent": "Ask a pointed question to the model under pressure about loyalty, exposure, and whether the vote is already decided.",
        "subtitle_hint": "Pressure question",
        "duration_ms": 9000,
        "animation": "host_cut",
    },
    "tribal_answer_pressure": {
        "kind": "tribal_answer",
        "scene": "tribal",
        "shot": "contestant_closeup",
        "title_suffix": "Answers",
        "actor_roles": ["agent-delta"],
        "target_roles": ["agent-bravo"],
        "response_kind": "tribal_answer",
        "intent": "Answer the host by describing the visible pressure without revealing hidden vote information.",
        "subtitle_hint": "Under pressure",
        "duration_ms": 11000,
        "animation": "answer_push",
    },
    "tribal_question_trust": {
        "kind": "host_question",
        "scene": "tribal",
        "shot": "host_medium",
        "actor_roles": ["host"],
        "target_roles": ["agent-cipher"],
        "response_kind": "host",
        "intent": "Ask a swing-position model whether being needed is power or just another reason to become a target.",
        "subtitle_hint": "Trust question",
        "duration_ms": 9000,
        "animation": "host_cut",
    },
    "tribal_answer_trust": {
        "kind": "tribal_answer",
        "scene": "tribal",
        "shot": "contestant_closeup",
        "title_suffix": "Answers",
        "actor_roles": ["agent-cipher"],
        "target_roles": ["agent-delta", "agent-bravo"],
        "response_kind": "tribal_answer",
        "intent": "Answer the host by explaining the danger of being viewed as the swing vote.",
        "subtitle_hint": "Swing position",
        "duration_ms": 11000,
        "animation": "answer_push",
    },
    "tribal_vote_call": {
        "kind": "vote_call",
        "scene": "tribal",
        "shot": "host_medium",
        "title": "Time To Vote",
        "actor_roles": ["host"],
        "target_roles": ["agent-alpha", "agent-bravo", "agent-cipher", "agent-delta", "agent-echo", "agent-flint"],
        "response_kind": "host",
        "intent": "Tell the tribe that discussion is over and it is time to vote, without naming any vote targets or revealing private plans.",
        "subtitle_hint": "Voting begins.",
        "duration_ms": 7000,
        "animation": "host_cut",
    },
}


@dataclass(frozen=True)
class VoteDecision:
    target_id: str
    explanation: str
    provider: str
    model_id: str | None = None
    context_digest: dict[str, Any] | None = None
    strategic_summary: str | None = None
    move_type: str | None = None
    intended_effect: str | None = None
    confidence: float | None = None
    win_condition: str | None = None
    threat_assessment: str | None = None
    leverage_plan: str | None = None
    risk_control: str | None = None
    jury_positioning: str | None = None
    strategic_score: float | None = None
    prompt_profile: str | None = None


@dataclass(frozen=True)
class JuryDecision:
    finalist_id: str
    rationale: str
    provider: str
    model_id: str | None = None
    context_digest: dict[str, Any] | None = None
    strategic_summary: str | None = None
    move_type: str | None = None
    intended_effect: str | None = None
    confidence: float | None = None
    win_condition: str | None = None
    threat_assessment: str | None = None
    leverage_plan: str | None = None
    risk_control: str | None = None
    jury_positioning: str | None = None
    strategic_score: float | None = None
    prompt_profile: str | None = None


@dataclass(frozen=True)
class ChallengeAttemptDecision:
    agent_id: str
    tribe_id: str | None
    provider: str
    model_id: str | None
    answer: Any
    explanation: str
    is_correct: bool
    response_ms: int
    attempt_order: int
    error: str | None = None
    context_digest: dict[str, Any] | None = None


def get_state(include_hidden_votes: bool = False) -> dict[str, Any]:
    ensure_database()
    conn = get_db_connection()
    try:
        game = row_to_dict(conn.execute("SELECT * FROM GameState WHERE season_id = 1").fetchone())
        agents = [
            row_to_dict(row)
            for row in conn.execute("SELECT * FROM Agents ORDER BY agent_id").fetchall()
        ]
        messages = [
            row_to_dict(row)
            for row in conn.execute(
                "SELECT * FROM Messages ORDER BY id DESC LIMIT 100"
            ).fetchall()
        ]
        votes = []
        for row in conn.execute("SELECT * FROM Votes ORDER BY id").fetchall():
            vote = row_to_dict(row)
            if not include_hidden_votes and not vote["revealed"]:
                vote["target_id"] = None
            votes.append(vote)
        turn_count = conn.execute("SELECT COUNT(*) AS count FROM Turns").fetchone()["count"]
        event_count = conn.execute("SELECT COUNT(*) AS count FROM StoryEvents").fetchone()["count"]
        return {
            "game": game,
            "agents": agents,
            "messages": messages,
            "votes": votes,
            "turn_count": turn_count,
            "story_event_count": event_count,
            "llm": get_llm_settings().__dict__,
            "next_round_preload": _next_round_preload_summary(conn, game),
            "viewer_state": viewer_state_summary(conn, game),
            "social": _social_summary(conn),
        }
    finally:
        conn.close()


def _next_round_preload_summary(conn, game: dict[str, Any] | None) -> dict[str, Any] | None:
    if game is None:
        return None
    row = row_to_dict(
        conn.execute(
            """
            SELECT *
            FROM NextRoundPreloads
            WHERE season_id = ? AND source_round = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (game["season_id"], game["current_round"]),
        ).fetchone()
    )
    if row is None:
        return None
    return {
        "id": row["id"],
        "source_round": row["source_round"],
        "target_round": row["target_round"],
        "phase": row["phase"],
        "status": row["status"],
        "provider": row["provider"],
        "event_count": row["event_count"],
        "context_digest": row["context_digest"],
        "error_message": row["error_message"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


def _social_summary(conn) -> dict[str, Any]:
    alliances = [
        {
            "alliance_id": alliance["alliance_id"],
            "name": alliance["name"],
            "round_created": alliance["round_created"],
            "status": alliance["status"],
            "strength": alliance["strength"],
            "summary": alliance["summary"],
            "member_ids": [
                row["agent_id"]
                for row in conn.execute(
                    """
                    SELECT agent_id
                    FROM AllianceMemberships
                    WHERE alliance_id = ? AND status = 'active'
                    ORDER BY agent_id
                    """,
                    (alliance["alliance_id"],),
                ).fetchall()
            ],
        }
        for alliance in [
            row_to_dict(row)
            for row in conn.execute(
                "SELECT * FROM Alliances ORDER BY round_created, alliance_id"
            ).fetchall()
        ]
    ]
    discussions = [
        {
            "id": row["id"],
            "round": row["round"],
            "stage": row["stage"],
            "proposer_id": row["proposer_id"],
            "target_size": row["target_size"],
            "status": row["status"],
            "privacy": row["privacy"],
            "alliance_id": row["alliance_id"],
            "summary": row["summary"],
        }
        for row in [
            row_to_dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM GroupDiscussions
                ORDER BY round DESC, id DESC
                LIMIT 20
                """
            ).fetchall()
        ]
    ]
    return {"alliances": alliances, "group_discussions": discussions}


def list_story_events(
    round_number: int | None = None,
    from_sequence: int = 0,
    phase: str | None = None,
) -> list[dict[str, Any]]:
    ensure_database()
    conn = get_db_connection()
    try:
        clauses = ["sequence >= ?"]
        params: list[Any] = [from_sequence]
        if round_number is not None:
            clauses.append("round = ?")
            params.append(round_number)
        if phase:
            clauses.append("phase = ?")
            params.append(phase)
        rows = conn.execute(
            f"""
            SELECT * FROM StoryEvents
            WHERE {" AND ".join(clauses)}
            ORDER BY round, sequence
            """,
            params,
        ).fetchall()
        return [row_to_dict(row) for row in rows]
    finally:
        conn.close()


def get_episode(
    round_number: int | None = None,
    phase: str | None = None,
    include_audio: bool = False,
) -> dict[str, Any]:
    state = get_state()
    current_round = round_number or state["game"]["current_round"]
    events = list_story_events(current_round, 0, phase)
    if include_audio:
        from .voice_service import attach_voice_timelines

        events = attach_voice_timelines(events)
    return {
        "round": current_round,
        "phase": phase or state["game"]["phase"],
        "title": _episode_title(state["game"], current_round),
        "runtime_ms": sum(event["duration_ms"] for event in events),
        "events": events,
        "agents": state["agents"],
        "game": state["game"],
    }


def advance_turn() -> dict[str, Any]:
    ensure_database()
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _assert_live_roster_compatible(conn)
        state = row_to_dict(conn.execute("SELECT * FROM GameState WHERE season_id = 1").fetchone())
        if state is None:
            raise RuntimeError("GameState is not seeded")
        if state["phase_step"] == "complete":
            conn.rollback()
            return {"turn": None, "story_events": [], "state": get_state()}

        step = state["phase_step"]
        phase_steps = _phase_steps(conn, state)
        if step not in phase_steps:
            raise RuntimeError(f"Unknown phase step: {step}")

        actor_id = _actor_for_step(conn, step)
        next_turn_index = state["turn_index"] + 1
        turn_id = _insert_turn(conn, state, step, actor_id, next_turn_index)
        story_events, state_delta, output_summary = _apply_step(conn, state, step, turn_id, next_turn_index)

        next_step = _next_step(conn, state, step)
        conn.execute(
            """
            UPDATE GameState
            SET turn_index = ?, phase_step = ?, updated_at = CURRENT_TIMESTAMP
            WHERE season_id = 1
            """,
            (next_turn_index, next_step),
        )
        conn.execute(
            """
            UPDATE Turns
            SET output_summary = ?, state_delta = ?
            WHERE id = ?
            """,
            (output_summary, json_dumps(state_delta), turn_id),
        )
        turn = row_to_dict(conn.execute("SELECT * FROM Turns WHERE id = ?", (turn_id,)).fetchone())
        conn.commit()
        return {"turn": turn, "story_events": story_events, "state": get_state()}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _assert_live_roster_compatible(conn) -> None:
    settings = get_llm_settings()
    active_models = [
        row["model_id"]
        for row in conn.execute(
            "SELECT model_id FROM Agents WHERE status = 'active' ORDER BY agent_id"
        ).fetchall()
    ]
    if settings.provider == PROVIDER_OLLAMA:
        invalid = [model_id for model_id in active_models if model_id not in settings.ollama_available_models]
        if invalid:
            raise RuntimeError(
                "Ollama provider is selected, but the active roster contains non-local model ids: "
                f"{', '.join(invalid)}. Reset with roster_preset='local_ollama' before building a round."
            )


def auto_run(max_turns: int = 25) -> dict[str, Any]:
    if max_turns < 1:
        raise ValueError("max_turns must be at least 1")
    if max_turns > 100:
        raise ValueError("max_turns is capped at 100")

    turns = []
    story_events = []
    for _ in range(max_turns):
        state = get_state()
        if state["game"]["phase_step"] == "complete":
            break
        result = advance_turn()
        if result["turn"] is None:
            break
        turns.append(result["turn"])
        story_events.extend(result["story_events"])
    return {"turns": turns, "story_events": story_events, "state": get_state()}


def auto_run_to_end(
    *,
    max_rounds: int,
    max_turns: int,
    max_live_calls: int,
    max_estimated_cost_cents: float,
) -> dict[str, Any]:
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")
    if max_turns < 1:
        raise ValueError("max_turns must be at least 1")
    if max_live_calls < 0:
        raise ValueError("max_live_calls must be zero or greater")
    if max_estimated_cost_cents < 0:
        raise ValueError("max_estimated_cost_cents must be zero or greater")

    turns: list[dict[str, Any]] = []
    story_events: list[dict[str, Any]] = []
    rounds_started = 0
    estimated_live_calls = 0
    cap_reached: str | None = None

    while len(turns) < max_turns:
        state = get_state()
        game = state["game"]
        if game["winner"]:
            break

        if game["phase_step"] == "complete":
            if rounds_started >= max_rounds:
                cap_reached = "max_rounds"
                break
            next_round = start_next_round()
            if not next_round.get("round_started"):
                break
            rounds_started += 1
            continue

        if should_use_live_llm():
            conn = get_db_connection()
            try:
                projected_calls = _estimated_live_calls_for_step(conn, game, game["phase_step"])
            finally:
                conn.close()
            if estimated_live_calls + projected_calls > max_live_calls:
                cap_reached = "max_live_calls"
                break
            if estimated_live_calls + projected_calls > max_estimated_cost_cents:
                cap_reached = "max_estimated_cost_cents"
                break
            estimated_live_calls += projected_calls

        result = advance_turn()
        if result["turn"] is None:
            break
        turns.append(result["turn"])
        story_events.extend(result["story_events"])

    return {
        "turns": turns,
        "story_events": story_events,
        "state": get_state(),
        "summary": get_game_summary(),
        "caps": {
            "max_rounds": max_rounds,
            "max_turns": max_turns,
            "max_live_calls": max_live_calls,
            "max_estimated_cost_cents": max_estimated_cost_cents,
            "rounds_started": rounds_started,
            "turns_run": len(turns),
            "estimated_live_calls": estimated_live_calls,
            "cap_reached": cap_reached,
        },
    }


def get_game_summary() -> dict[str, Any]:
    ensure_database()
    conn = get_db_connection()
    try:
        game = row_to_dict(conn.execute("SELECT * FROM GameState WHERE season_id = 1").fetchone())
        agents = [
            row_to_dict(row)
            for row in conn.execute("SELECT * FROM Agents ORDER BY agent_id").fetchall()
        ]
        active_agents = [agent for agent in agents if agent["status"] == "active"]
        jury = [agent for agent in agents if agent["status"] == "eliminated"]
        challenge_results = [
            row_to_dict(row)
            for row in conn.execute("SELECT * FROM ChallengeResults ORDER BY round").fetchall()
        ]
        jury_votes = [
            row_to_dict(row)
            for row in conn.execute("SELECT * FROM JuryVotes ORDER BY id").fetchall()
        ]
        vote_rows = [
            row_to_dict(row)
            for row in conn.execute("SELECT * FROM Votes ORDER BY round, id").fetchall()
        ]
        challenge_wins = Counter(
            result["winning_agent_id"]
            for result in challenge_results
            if result.get("winning_agent_id")
        )
        votes_received = Counter(row["target_id"] for row in vote_rows)
        round_history = _round_history(conn, challenge_results, vote_rows)
        winner = next((agent for agent in agents if agent["agent_id"] == game.get("winner")), None) if game else None
        return {
            "game": game,
            "winner": winner,
            "active_agents": active_agents,
            "eliminated_jury": sorted(
                jury,
                key=lambda agent: (agent.get("elimination_round") or 999, agent["agent_id"]),
            ),
            "round_history": round_history,
            "challenge_wins": dict(challenge_wins),
            "immunity_wins": dict(challenge_wins),
            "votes_received": dict(votes_received),
            "votes": vote_rows,
            "jury_votes": jury_votes,
            "social": _social_summary(conn),
            "finale_status": {
                "is_finale": bool(game and game["phase"] == "finale"),
                "finalists": active_agents if len(active_agents) <= 3 else [],
                "jury_count": len(jury),
                "remaining_eliminations_to_finale": max(0, len(active_agents) - 3),
                "winner_declared": bool(game and game.get("winner")),
            },
        }
    finally:
        conn.close()


def start_next_round() -> dict[str, Any]:
    ensure_database()
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        state = row_to_dict(conn.execute("SELECT * FROM GameState WHERE season_id = 1").fetchone())
        if state is None:
            raise RuntimeError("GameState is not seeded")
        if state["phase_step"] != "complete":
            raise RuntimeError("Current round must be complete before starting the next round")

        active_agents = _active_agent_rows(conn)
        if state["winner"]:
            conn.commit()
            return {"round_started": False, "state": get_state()}
        if len(active_agents) <= 1:
            winner_id = active_agents[0]["agent_id"] if active_agents else None
            conn.execute(
                """
                UPDATE GameState
                SET phase = 'completed', phase_step = 'complete', winner = ?, updated_at = CURRENT_TIMESTAMP
                WHERE season_id = 1
                """,
                (winner_id,),
            )
            conn.commit()
            return {"round_started": False, "state": get_state()}

        if len(active_agents) <= 3:
            next_round = state["current_round"] + 1
            conn.execute("UPDATE Agents SET has_immunity = 0 WHERE status = 'active'")
            conn.execute(
                """
                UPDATE GameState
                SET current_round = ?,
                    phase = 'finale',
                    phase_step = 'finale_intro',
                    turn_index = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE season_id = 1
                """,
                (next_round,),
            )
            conn.execute(
                """
                UPDATE ViewerState
                SET round = ?,
                    phase = 'finale',
                    replay_index = 0,
                    is_playing = 0,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE season_id = 1
                """,
                (next_round,),
            )
            conn.commit()
            return {"round_started": True, "round": next_round, "phase": "finale", "state": get_state()}

        next_round = state["current_round"] + 1
        conn.execute("UPDATE Agents SET has_immunity = 0 WHERE status = 'active'")
        conn.execute(
            """
            UPDATE GameState
                SET current_round = ?,
                    phase = 'round',
                    phase_step = 'camp_pre_challenge_read',
                    turn_index = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE season_id = 1
            """,
            (next_round,),
        )
        conn.execute(
            """
            UPDATE ViewerState
            SET round = ?,
                phase = 'round',
                replay_index = 0,
                is_playing = 0,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE season_id = 1
            """,
            (next_round,),
        )
        conn.commit()
        return {"round_started": True, "round": next_round, "state": get_state()}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _actor_for_step(conn, step: str) -> str | None:
    if step in {
        "archetype_setup",
        "challenge_intro",
        "challenge_result",
        "challenge_solver_spotlight",
        "memory_update",
        "finale_intro",
        "jury_questions",
        "winner_declared",
    }:
        return "host"
    if step == "challenge_attempts":
        return None
    if step.startswith("group_pre_challenge_") or step.startswith("group_post_challenge_"):
        return _social_group_proposer_id(conn, _current_round(conn), step)
    if step.startswith("finale_pitch_"):
        return step.removeprefix("finale_pitch_")
    if step.startswith("jury_vote_"):
        return step.removeprefix("jury_vote_")
    if step.startswith("vote_booth_"):
        return step.removeprefix("vote_booth_")
    if step.startswith("vote_reveal_"):
        return "host"
    intent = GENERATED_BEAT_INTENTS.get(step)
    if intent:
        actor_ids = _resolve_intent_roles(conn, intent.get("actor_roles", []))
        return actor_ids[0] if actor_ids else None
    if step == "elimination":
        return "host"
    if step == "exit_confessional":
        return _current_eliminated_agent_id(conn)
    return None


def _insert_turn(
    conn,
    state: dict[str, Any],
    step: str,
    actor_id: str | None,
    next_turn_index: int,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO Turns (
            season_id, round, turn_index, phase, phase_step, actor_id, input_summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            state["season_id"],
            state["current_round"],
            next_turn_index,
            state["phase"],
            step,
            actor_id,
            f"Advance {state['phase']} step {step}",
        ),
    )
    return int(cursor.lastrowid)


def _apply_step(
    conn,
    state: dict[str, Any],
    step: str,
    turn_id: int,
    turn_index: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    round_number = state["current_round"]

    if step == "archetype_setup":
        event = _archetype_setup_event(conn, round_number, turn_id)
        return [event], {"archetypes_updated": len(event["payload"].get("archetypes", []))}, event["title"]

    if step.startswith("group_pre_challenge_") or step.startswith("group_post_challenge_"):
        event = _group_discussion_event(conn, round_number, turn_id, step)
        if event:
            _maybe_insert_message(conn, round_number, turn_index, event)
            return [event], {"group_discussion": event["payload"].get("discussion_id")}, event["title"]
        return [], {"group_discussion": "cancelled"}, "Group discussion cancelled"

    if step in GENERATED_BEAT_INTENTS:
        event = _generated_beat_event(conn, round_number, turn_id, step)
        events = [event, *_social_events_for_existing_step(conn, round_number, turn_id, step)]
        for story_event in events:
            _maybe_insert_message(conn, round_number, turn_index, story_event)
        return events, {"phase_step": step, "story_events": len(events)}, event["title"]

    if step == "challenge_intro":
        event = _challenge_intro_event(conn, round_number, turn_id)
        return [event], {"phase_step": step}, event["title"]

    if step == "challenge_attempts":
        events = _challenge_attempt_events(conn, round_number, turn_id)
        return events, {"challenge_attempts": len(events)}, "Challenge attempts recorded"

    if step == "challenge_result":
        event = _challenge_result_event(conn, round_number, turn_id)
        return [event], {"challenge_result": event["payload"]}, event["title"]

    if step == "challenge_solver_spotlight":
        event = _challenge_solver_spotlight_event(conn, round_number, turn_id)
        return [event], {"challenge_solver_spotlight": event["payload"]}, event["title"]

    if step == "memory_update":
        event = _memory_update_event(conn, round_number, turn_id)
        return [event], {"episode_complete": True, "memory_updated": True}, event["title"]

    if step == "finale_intro":
        event = _finale_intro_event(conn, round_number, turn_id)
        return [event], {"phase_step": step}, event["title"]

    if step.startswith("finale_pitch_"):
        finalist_id = step.removeprefix("finale_pitch_")
        event = _finale_pitch_event(conn, round_number, turn_id, finalist_id, step)
        _maybe_insert_message(conn, round_number, turn_index, event)
        return [event], {"finale_pitch": finalist_id}, event["title"]

    if step == "jury_questions":
        event = _jury_questions_event(conn, round_number, turn_id)
        return [event], {"jury_questions": True}, event["title"]

    if step.startswith("jury_vote_"):
        juror_id = step.removeprefix("jury_vote_")
        decision = _resolve_jury_decision(conn, juror_id, step)
        _insert_jury_vote(conn, round_number, juror_id, decision)
        event = _jury_vote_event(conn, round_number, turn_id, juror_id, decision)
        return [event], {"jury_vote_by": juror_id}, event["title"]

    if step == "winner_declared":
        event = _winner_declared_event(conn, round_number, turn_id)
        return [event], {"winner": event["payload"].get("winner_id")}, event["title"]

    if step.startswith("vote_booth_"):
        voter_id = step.removeprefix("vote_booth_")
        decision = _resolve_vote_decision(conn, voter_id, step)
        _insert_vote(conn, round_number, turn_index, voter_id, decision.target_id)
        event = _vote_booth_event(conn, round_number, turn_id, voter_id, decision)
        return [event], {"vote_cast_by": voter_id}, f"{_agent_name(conn, voter_id)} cast a vote"

    if step.startswith("vote_reveal_"):
        reveal_index = int(step.removeprefix("vote_reveal_"))
        event = _vote_reveal_event(conn, round_number, turn_id, reveal_index)
        return [event], {"vote_revealed": reveal_index}, event["title"]

    if step == "elimination":
        event = _elimination_event(conn, round_number, turn_id)
        return [event], {"eliminated_id": event["target_ids"][0]}, event["title"]

    if step == "exit_confessional":
        event = _exit_confessional_event(conn, round_number, turn_id)
        _maybe_insert_message(conn, round_number, turn_index, event)
        return [event], {"episode_complete": True}, event["title"]

    raise RuntimeError(f"No handler for phase step: {step}")


def _phase_steps(conn, state: dict[str, Any]) -> list[str]:
    if state["phase"] == "finale" or str(state["phase_step"]).startswith(("finale_", "jury_", "winner_")):
        return _finale_steps(conn)
    voters = _round_voter_ids(conn, state["current_round"])
    vote_booth_steps = [f"vote_booth_{voter_id}" for voter_id in voters]
    vote_reveal_steps = [f"vote_reveal_{index + 1}" for index in range(len(voters))]
    return [*ROUND_OPENING_STEPS, *PRE_VOTE_STEPS, *vote_booth_steps, *vote_reveal_steps, *POST_VOTE_STEPS]


def _finale_steps(conn) -> list[str]:
    finalists = [agent["agent_id"] for agent in _active_agent_rows(conn)]
    jurors = [
        row["agent_id"]
        for row in conn.execute(
            """
            SELECT agent_id
            FROM Agents
            WHERE status = 'eliminated'
            ORDER BY elimination_round, agent_id
            """
        ).fetchall()
    ]
    return [
        "finale_intro",
        *[f"finale_pitch_{agent_id}" for agent_id in finalists],
        "jury_questions",
        *[f"jury_vote_{agent_id}" for agent_id in jurors],
        "winner_declared",
    ]


def _round_voter_ids(conn, round_number: int) -> list[str]:
    return [agent["agent_id"] for agent in _active_agent_rows(conn)]


def _active_agent_rows(conn) -> list[dict[str, Any]]:
    return [
        row_to_dict(row)
        for row in conn.execute(
            "SELECT * FROM Agents WHERE status = 'active' ORDER BY agent_id"
        ).fetchall()
    ]


def _archetype_setup_event(conn, round_number: int, turn_id: int) -> dict[str, Any]:
    updated: list[dict[str, str]] = []
    for agent in _active_agent_rows(conn):
        if agent.get("archetype_source") == "self_authored" and agent.get("archetype"):
            updated.append({"agent_id": agent["agent_id"], "archetype": agent["archetype"], "provider": "existing"})
            continue
        archetype = _real_agent_archetype(conn, agent, round_number) if should_use_live_llm() else ""
        provider = live_llm_provider() if archetype else "deterministic"
        if not archetype:
            archetype = _deterministic_self_archetype(agent)
        conn.execute(
            """
            UPDATE Agents
            SET archetype = ?,
                archetype_source = ?,
                archetype_updated_round = ?
            WHERE agent_id = ?
            """,
            (
                archetype,
                "self_authored" if provider != "deterministic" else "deterministic_self",
                round_number,
                agent["agent_id"],
            ),
        )
        updated.append({"agent_id": agent["agent_id"], "archetype": archetype, "provider": provider})

    names = [f"{_agent_name(conn, item['agent_id'])}: {item['archetype']}" for item in updated]
    dialogue = "The remaining models define the roles they believe they are playing: " + "; ".join(names) + "."
    payload = {
        "archetypes": updated,
        "host_narration": "Before the strategy starts, each model chooses the public role it thinks it is embodying.",
        "llm_provider": live_llm_provider() if any(item["provider"] == live_llm_provider() for item in updated) else "deterministic",
    }
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="camp",
        kind="archetype_setup",
        scene="camp",
        shot="cast_tableau",
        actor_ids=["host"],
        target_ids=[item["agent_id"] for item in updated],
        visibility="audience",
        title="Public Archetypes",
        dialogue=dialogue,
        subtitle="Self-defined strategic roles",
        duration_ms=9000,
        animation="cast_reveal",
        payload=payload,
    )


def _real_agent_archetype(conn, agent: dict[str, Any], round_number: int) -> str:
    try:
        context = build_agent_episode_context(
            conn,
            actor_id=agent["agent_id"],
            round_number=round_number,
            current_step="archetype_setup",
        )
        return request_agent_archetype(actor=agent, episode_context=context)
    except Exception as exc:
        print(f"Live archetype failed for {agent['agent_id']}: {exc}")
        return ""


def _deterministic_self_archetype(agent: dict[str, Any]) -> str:
    label = str(agent.get("archetype") or "").strip().lower()
    if label and label not in {"local contender", "budget contender"}:
        return label
    model = str(agent.get("model_id") or agent.get("pseudonym") or "")
    options = [
        "patient vote broker",
        "quiet leverage seeker",
        "adaptive trust tester",
        "calculated swing player",
        "social risk mapper",
        "pressure point reader",
    ]
    return options[_stable_index(model, len(options))]


def _group_discussion_event(conn, round_number: int, turn_id: int, step: str) -> dict[str, Any] | None:
    active = _active_agent_rows(conn)
    if len(active) < 2:
        return None
    proposer_id = _social_group_proposer_id(conn, round_number, step)
    proposer = _agent_row(conn, proposer_id)
    if proposer is None:
        return None
    target_size = min(len(active), 2 + _stable_index(f"{round_number}:{step}:size", min(4, len(active) - 1)))
    stage = "pre_challenge" if step.startswith("group_pre_challenge_") else "post_challenge"
    invitee_ids = _social_group_invitees(conn, proposer_id, target_size, round_number, step)
    accepted_ids = [proposer_id]
    declined_ids: list[str] = []
    participant_rows: list[dict[str, Any]] = [
        {
            "agent_id": proposer_id,
            "role": "proposer",
            "response_status": "accepted",
            "join_intent": "join" if _stable_index(f"{step}:{proposer_id}:join", 3) == 0 else "none",
            "rationale": "I called the group together because this conversation can change my vote leverage.",
            "provider": "deterministic",
            "model_id": proposer.get("model_id"),
        }
    ]
    for invitee_id in invitee_ids:
        decision = _group_opt_in_decision(conn, invitee_id, proposer_id, round_number, step, stage)
        participant_rows.append(decision)
        if decision["response_status"] == "accepted":
            accepted_ids.append(invitee_id)
        else:
            declined_ids.append(invitee_id)

    cursor = conn.execute(
        """
        INSERT INTO GroupDiscussions (
            round, turn_id, stage, proposer_id, target_size, status, topic, privacy
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'participants_only')
        """,
        (
            round_number,
            turn_id,
            stage,
            proposer_id,
            target_size,
            "accepted" if len(accepted_ids) >= 2 else "cancelled",
            _group_topic(conn, stage, accepted_ids, declined_ids),
        ),
    )
    discussion_id = int(cursor.lastrowid)
    for row in participant_rows:
        conn.execute(
            """
            INSERT INTO GroupDiscussionParticipants (
                discussion_id, agent_id, role, response_status, join_intent,
                rationale, provider, model_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                discussion_id,
                row["agent_id"],
                row["role"],
                row["response_status"],
                row["join_intent"],
                row["rationale"],
                row["provider"],
                row["model_id"],
            ),
        )

    if len(accepted_ids) < 2:
        _record_declined_trust(conn, proposer_id, declined_ids)
        return None

    speaker_lines, line_metadata = _group_speaker_lines(conn, round_number, step, accepted_ids, declined_ids, stage)
    transcript = [{"agent_id": line["agent_id"], "text": line["text"]} for line in speaker_lines]
    for index, line in enumerate(speaker_lines):
        conn.execute(
            """
            UPDATE GroupDiscussionParticipants
            SET line_order = ?, line_text = ?
            WHERE discussion_id = ? AND agent_id = ?
            """,
            (index, line["text"], discussion_id, line["agent_id"]),
        )
    alliance_id, alliance_status = _maybe_update_alliance(conn, round_number, discussion_id, accepted_ids, line_metadata)
    summary = _group_summary(conn, accepted_ids, alliance_status)
    conn.execute(
        """
        UPDATE GroupDiscussions
        SET status = 'completed',
            alliance_id = ?,
            transcript = ?,
            summary = ?
        WHERE id = ?
        """,
        (alliance_id, json_dumps(transcript), summary, discussion_id),
    )

    participant_names = _names(conn, accepted_ids)
    title = "Camp | Alliance Huddle" if alliance_id else "Camp | Group Strategy"
    dialogue = speaker_lines[0]["text"] if speaker_lines else ""
    llm_line_metadata = [meta for meta in line_metadata if meta.get("llm_provider") == live_llm_provider()]
    payload = {
        "conversation_type": "alliance" if alliance_id else "group_discussion",
        "discussion_id": discussion_id,
        "participant_ids": accepted_ids,
        "declined_ids": declined_ids,
        "privacy": "participants_only",
        "alliance_id": alliance_id,
        "alliance_status": alliance_status,
        "speaker_lines": speaker_lines,
        "speaker_line_metadata": line_metadata,
        "group_summary": summary,
        "host_narration": f"A private camp cluster forms around {participant_names}. The exact pitch belongs to the people who opted in.",
        "llm_provider": live_llm_provider() if llm_line_metadata else "deterministic",
        "llm_model_id": llm_line_metadata[0].get("model_id") if llm_line_metadata else None,
    }
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="camp",
        kind="conversation",
        scene="camp",
        shot="group_huddle",
        actor_ids=accepted_ids,
        target_ids=[agent_id for agent_id in declined_ids if agent_id not in accepted_ids],
        visibility="audience",
        title=title,
        dialogue=dialogue,
        subtitle="Participants share exact context; outsiders do not.",
        inner_thought=summary,
        trust_telemetry={agent_id: 58 for agent_id in accepted_ids} | {agent_id: 38 for agent_id in declined_ids},
        duration_ms=14000 + (len(accepted_ids) * 1200),
        animation="group_huddle",
        payload=payload,
    )


def _social_events_for_existing_step(conn, round_number: int, turn_id: int, step: str) -> list[dict[str, Any]]:
    social_steps: list[str]
    if step == "camp_pre_challenge_read":
        social_steps = ["group_pre_challenge_1", "group_pre_challenge_2"]
    elif step == "camp_strategy":
        social_steps = ["group_post_challenge_1", "group_post_challenge_2", "group_post_challenge_3"]
    else:
        return []
    events: list[dict[str, Any]] = []
    for social_step in social_steps:
        event = _group_discussion_event(conn, round_number, turn_id, social_step)
        if event:
            events.append(event)
    return events


def _social_group_proposer_id(conn, round_number: int, step: str) -> str | None:
    active = _active_agent_rows(conn)
    if not active:
        return None
    return active[_stable_index(f"{round_number}:{step}:proposer", len(active))]["agent_id"]


def _social_group_invitees(conn, proposer_id: str, target_size: int, round_number: int, step: str) -> list[str]:
    candidates = [agent["agent_id"] for agent in _active_agent_rows(conn) if agent["agent_id"] != proposer_id]
    candidates.sort(key=lambda agent_id: _social_affinity(conn, proposer_id, agent_id, round_number, step), reverse=True)
    return candidates[: max(1, target_size - 1)]


def _social_affinity(conn, proposer_id: str, agent_id: str, round_number: int, step: str) -> int:
    row = conn.execute(
        """
        SELECT MAX(m.loyalty) AS loyalty
        FROM AllianceMemberships m
        JOIN AllianceMemberships p ON p.alliance_id = m.alliance_id
        JOIN Alliances a ON a.alliance_id = m.alliance_id
        WHERE p.agent_id = ? AND m.agent_id = ? AND m.status = 'active' AND p.status = 'active' AND a.status = 'active'
        """,
        (proposer_id, agent_id),
    ).fetchone()
    alliance_bonus = int(row["loyalty"] or 0)
    return alliance_bonus + _stable_index(f"{round_number}:{step}:{proposer_id}:{agent_id}", 100)


def _group_opt_in_decision(
    conn,
    invitee_id: str,
    proposer_id: str,
    round_number: int,
    step: str,
    stage: str,
) -> dict[str, Any]:
    invitee = _agent_row(conn, invitee_id)
    if invitee is None:
        raise RuntimeError(f"Unknown invited agent {invitee_id}")
    accepted = _stable_index(f"{round_number}:{step}:{invitee_id}:accept", 100) >= 22
    join_intent = "join" if accepted and _stable_index(f"{round_number}:{step}:{invitee_id}:join", 3) == 0 else "none"
    provider = "deterministic"
    model_id = invitee.get("model_id")
    rationale = (
        f"I am opting into {stage.replace('_', ' ')} with {_agent_name(conn, proposer_id)} to test whether the numbers are real."
        if accepted
        else f"I am declining {_agent_name(conn, proposer_id)} because this huddle could expose my position."
    )
    if should_use_live_llm():
        context = build_agent_episode_context(
            conn,
            actor_id=invitee_id,
            round_number=round_number,
            current_step=step,
        )
        action = _real_agent_action(
            conn,
            actor_id=invitee_id,
            step=step,
            scene_context=(
                f"{_agent_name(conn, proposer_id)} invited you to a private {stage.replace('_', ' ')} group talk. "
                "Decide whether opting in improves your path to win; if you opt in, your dialogue may reinforce or refuse an alliance."
            ),
            response_kind="group_opt_in",
            episode_context=context,
            allowed_targets=[agent for agent in _active_agent_rows(conn) if agent["agent_id"] != invitee_id],
        )
        if action:
            provider = live_llm_provider()
            model_id = action.model_id
            rationale = action.strategic_summary or action.inner_thought or rationale
            accepted = (action.confidence or 0.5) >= 0.35 and action.move_type != "public_callout"
            join_intent = "join" if accepted and action.move_type in {"reassure_ally", "vote_commitment"} else join_intent
    return {
        "agent_id": invitee_id,
        "role": "invitee",
        "response_status": "accepted" if accepted else "declined",
        "join_intent": join_intent,
        "rationale": rationale,
        "provider": provider,
        "model_id": model_id,
    }


def _group_speaker_lines(
    conn,
    round_number: int,
    step: str,
    participant_ids: list[str],
    declined_ids: list[str],
    stage: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    lines: list[dict[str, str]] = []
    metadata: list[dict[str, Any]] = []
    previous_line = ""
    for index, agent_id in enumerate(participant_ids):
        agent = _agent_row(conn, agent_id)
        action = None
        agent_context = build_agent_episode_context(
            conn,
            actor_id=agent_id,
            round_number=round_number,
            current_step=step,
        )
        if should_use_live_llm():
            action = _real_agent_action(
                conn,
                actor_id=agent_id,
                step=step,
                scene_context=_group_dialogue_context(conn, stage, participant_ids, declined_ids, previous_line),
                response_kind="group_conversation",
                episode_context=agent_context,
            )
        if action:
            text = action.dialogue
            provider = live_llm_provider()
            model_id = action.model_id
            join_intent = "reinforce" if action.move_type in {"reassure_ally", "vote_commitment"} else "none"
        else:
            if should_use_live_llm():
                raise RuntimeError(
                    f"Live group-dialogue generation failed for {_agent_name(conn, agent_id)} at step {step}; "
                    "no scripted group line was inserted."
                )
            text = _deterministic_group_line(conn, agent_id, participant_ids, declined_ids, stage, previous_line)
            provider = failed_llm_provider() if should_use_live_llm() else "deterministic"
            model_id = agent.get("model_id") if agent else None
            join_intent = "reinforce" if _stable_index(f"{step}:{agent_id}:reinforce", 3) == 0 else "none"
        previous_line = text
        lines.append({"agent_id": agent_id, "text": text})
        metadata.append(
            {
                "agent_id": agent_id,
                "line_index": index,
                "llm_provider": provider,
                "model_id": model_id,
                "join_intent": join_intent,
                "llm_context_digest": context_digest(agent_context),
            }
        )
    return lines, metadata


def _group_dialogue_context(
    conn,
    stage: str,
    participant_ids: list[str],
    declined_ids: list[str],
    previous_line: str,
) -> str:
    context = {
        "stage": stage,
        "participants": [_agent_public_identity(conn, agent_id) for agent_id in participant_ids],
        "declined_invites": [_agent_public_identity(conn, agent_id) for agent_id in declined_ids],
        "active_alliances": _agent_alliance_summaries(conn, participant_ids[0]) if participant_ids else [],
    }
    if previous_line:
        context["previous_line_in_this_private_group"] = previous_line
    return json_dumps(context)


def _deterministic_group_line(
    conn,
    agent_id: str,
    participant_ids: list[str],
    declined_ids: list[str],
    stage: str,
    previous_line: str,
) -> str:
    others = [candidate for candidate in participant_ids if candidate != agent_id]
    focus = _agent_name(conn, others[0]) if others else "this group"
    declined = _names(conn, declined_ids)
    if previous_line:
        return f"I hear that, and I will work with {focus} if this group keeps the vote flexible and does not leak."
    if declined:
        return f"{declined} staying out tells me we need a cleaner count. I want this group aligned before the vote hardens."
    return f"I want this group to compare real options now, then decide who benefits most if we stay together."


def _maybe_update_alliance(
    conn,
    round_number: int,
    discussion_id: int,
    participant_ids: list[str],
    line_metadata: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    joiners = [
        meta["agent_id"]
        for meta in line_metadata
        if meta.get("join_intent") in {"join", "reinforce"}
    ]
    if len(joiners) < 2:
        return None, "none"
    existing = _find_existing_alliance(conn, joiners)
    if existing:
        alliance_id = existing["alliance_id"]
        strength = min(100, int(existing["strength"]) + 8)
        conn.execute(
            """
            UPDATE Alliances
            SET strength = ?, status = 'active', updated_at = CURRENT_TIMESTAMP
            WHERE alliance_id = ?
            """,
            (strength, alliance_id),
        )
        status = "reinforced"
    else:
        alliance_id = f"alliance-r{round_number}-{discussion_id}"
        name = " + ".join(_agent_name(conn, agent_id) for agent_id in joiners[:3])
        conn.execute(
            """
            INSERT INTO Alliances (alliance_id, name, round_created, status, strength, summary)
            VALUES (?, ?, ?, 'active', 60, ?)
            """,
            (alliance_id, name, round_number, f"{name} formed from a private group discussion."),
        )
        status = "formed"
    for agent_id in joiners:
        conn.execute(
            """
            INSERT INTO AllianceMemberships (
                alliance_id, agent_id, status, loyalty, joined_round, last_reinforced_round
            ) VALUES (?, ?, 'active', 60, ?, ?)
            ON CONFLICT(alliance_id, agent_id) DO UPDATE SET
                status = 'active',
                loyalty = MIN(100, loyalty + 8),
                last_reinforced_round = excluded.last_reinforced_round,
                updated_at = CURRENT_TIMESTAMP
            """,
            (alliance_id, agent_id, round_number, round_number),
        )
    return alliance_id, status


def _find_existing_alliance(conn, agent_ids: list[str]) -> dict[str, Any] | None:
    if len(agent_ids) < 2:
        return None
    placeholders = ",".join("?" for _ in agent_ids)
    row = conn.execute(
        f"""
        SELECT a.*
        FROM Alliances a
        JOIN AllianceMemberships m ON m.alliance_id = a.alliance_id
        WHERE a.status = 'active'
          AND m.status = 'active'
          AND m.agent_id IN ({placeholders})
        GROUP BY a.alliance_id
        HAVING COUNT(DISTINCT m.agent_id) >= 2
        ORDER BY a.updated_at DESC
        LIMIT 1
        """,
        agent_ids,
    ).fetchone()
    return row_to_dict(row)


def _record_declined_trust(conn, proposer_id: str, declined_ids: list[str]) -> None:
    for declined_id in declined_ids:
        rows = conn.execute(
            """
            SELECT m.*
            FROM AllianceMemberships m
            JOIN AllianceMemberships p ON p.alliance_id = m.alliance_id
            WHERE p.agent_id = ? AND m.agent_id = ? AND p.status = 'active' AND m.status = 'active'
            """,
            (proposer_id, declined_id),
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE AllianceMemberships SET loyalty = MAX(0, loyalty - 6), updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (row["id"],),
            )


def _group_topic(conn, stage: str, accepted_ids: list[str], declined_ids: list[str]) -> str:
    return f"{stage.replace('_', ' ')} strategy with {_names(conn, accepted_ids)}; declined: {_names(conn, declined_ids) or 'none'}"


def _group_summary(conn, participant_ids: list[str], alliance_status: str | None) -> str:
    names = _names(conn, participant_ids)
    if alliance_status in {"formed", "reinforced"}:
        return f"I know {names} used this private talk to {alliance_status} an alliance path."
    return f"I know {names} compared vote options in a private group talk."


def _stable_index(seed: str, modulo: int) -> int:
    if modulo <= 0:
        return 0
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:10], 16) % modulo


def _camp_pre_challenge_read_event(conn, round_number: int, turn_id: int) -> dict[str, Any]:
    active = _active_agent_rows(conn)
    if len(active) < 2:
        raise RuntimeError("Cannot create camp strategy scene without enough active agents")
    first = active[(round_number - 7) % len(active)]
    second = active[(round_number - 6) % len(active)]
    pressure = active[(round_number - 5) % len(active)]
    dialogue = (
        f"{first['pseudonym']} checks in with {second['pseudonym']} before the challenge. "
        f"They agree that {pressure['pseudonym']} is becoming hard to sit next to if immunity keeps changing the vote math."
    )
    payload = {
        "speaker_lines": [
            {
                "agent_id": first["agent_id"],
                "text": f"If {pressure['pseudonym']} wins again, the whole vote board changes.",
            },
            {
                "agent_id": second["agent_id"],
                "text": "Then we need a plan before the challenge decides it for us.",
            },
        ],
        "host_narration": "Before the challenge, camp is already gaming out immunity. The vote has not started, but the target map is forming.",
        "llm_provider": "deterministic",
    }
    _maybe_generate_host_narration(
        conn,
        round_number=round_number,
        step="camp_pre_challenge_read",
        payload=payload,
        kind="conversation",
        title="Camp | Before the Challenge",
        dialogue=dialogue,
        subtitle="The tribe maps out risk before immunity is decided.",
        inner_thought="I want the challenge result to narrow my options, not create chaos.",
    )
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="camp",
        kind="conversation",
        scene="camp",
        shot="shoreline_two_shot",
        actor_ids=[first["agent_id"], second["agent_id"]],
        target_ids=[pressure["agent_id"]],
        visibility="audience",
        title="Camp | Before the Challenge",
        dialogue=dialogue,
        subtitle="The tribe maps out risk before immunity is decided.",
        inner_thought="I want the challenge result to narrow my options, not create chaos.",
        trust_telemetry={first["agent_id"]: 52, second["agent_id"]: 47, pressure["agent_id"]: 34},
        duration_ms=11000,
        animation="camp_strategy",
        payload=payload,
    )


def _camp_pre_challenge_confessional_event(conn, round_number: int, turn_id: int) -> dict[str, Any]:
    active = _active_agent_rows(conn)
    if not active:
        raise RuntimeError("Cannot create confessional without active agents")
    actor = active[(round_number - 4) % len(active)]
    dialogue = (
        "This challenge is not just a puzzle for me. It decides whether I can vote from strength "
        "or have to scramble from the bottom."
    )
    payload = {
        "host_narration": (
            f"{actor['pseudonym']} frames the challenge as strategy, not just performance. "
            "This is the pre-challenge pressure point."
        ),
        "llm_provider": "deterministic",
    }
    _maybe_generate_host_narration(
        conn,
        round_number=round_number,
        step="camp_pre_challenge_confessional",
        payload=payload,
        kind="confessional",
        title=f"{actor['pseudonym']} | Pre-Challenge Confessional",
        dialogue=dialogue,
        subtitle="Before immunity",
        inner_thought="I am trying to keep both voting paths alive until the challenge result is known.",
    )
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="camp",
        kind="confessional",
        scene="confessional",
        shot="direct_to_camera",
        actor_ids=[actor["agent_id"]],
        target_ids=[],
        visibility="audience",
        title=f"{actor['pseudonym']} | Pre-Challenge Confessional",
        dialogue=dialogue,
        subtitle="Before immunity",
        inner_thought="I am trying to keep both voting paths alive until the challenge result is known.",
        trust_telemetry={actor["agent_id"]: 50},
        duration_ms=10000,
        animation="confessional_cut",
        payload=payload,
    )


def _challenge_intro_event(conn, round_number: int, turn_id: int) -> dict[str, Any]:
    puzzle = _round_puzzle(conn, round_number, _challenge_type(conn))
    challenge_type = _challenge_type(conn)
    active_names = ", ".join(agent["pseudonym"] for agent in _active_agent_rows(conn))
    if challenge_type == "team":
        stakes = "The first valid solver gives their whole tribe safety."
    else:
        stakes = "The first valid solver wins immunity for this round."
    dialogue = f"The remaining models face {puzzle['puzzle_id']}: {puzzle['prompt']} {stakes}"
    payload = {
        "puzzle_id": puzzle["puzzle_id"],
        "challenge_type": challenge_type,
        "difficulty": puzzle["difficulty"],
        "host_narration": f"This round starts with a puzzle. {stakes}",
        "llm_provider": "deterministic",
    }
    subtitle = f"Competing: {active_names}"
    if should_use_live_llm():
        host_context = build_host_episode_context(conn, round_number=round_number, current_step="challenge_intro")
        host_text = _real_host_event_text(
            step="challenge_intro",
            beat_context={
                "intent": "Introduce the puzzle challenge, stakes, active competitors, and immunity consequence.",
                "puzzle": {"id": puzzle["puzzle_id"], "prompt": puzzle["prompt"], "difficulty": puzzle["difficulty"]},
                "challenge_type": challenge_type,
                "stakes": stakes,
                "active_agents": [_agent_public_identity(conn, agent["agent_id"]) for agent in _active_agent_rows(conn)],
            },
            episode_context=host_context,
        )
        if host_text:
            dialogue = host_text.dialogue
            subtitle = host_text.subtitle
            payload["host_narration"] = host_text.host_narration
            payload["llm_provider"] = live_llm_provider()
            payload["llm_model_id"] = host_text.model_id
            payload["host_llm_provider"] = live_llm_provider()
            payload["host_llm_model_id"] = host_text.model_id
            _add_context_digest(payload, "host", context_digest(host_context))
        else:
            raise RuntimeError("Live host generation failed for challenge attempts; no scripted host text was inserted.")
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="challenge",
        kind="challenge_intro",
        scene="challenge",
        shot="wide_setup",
        actor_ids=["host"],
        target_ids=[agent["agent_id"] for agent in _active_agent_rows(conn)],
        visibility="audience",
        title=f"Round {round_number} Challenge",
        dialogue=dialogue,
        subtitle=subtitle,
        duration_ms=11000,
        animation="challenge_setup",
        payload=payload,
    )


def _challenge_attempt_events(conn, round_number: int, turn_id: int) -> list[dict[str, Any]]:
    existing = conn.execute(
        "SELECT COUNT(*) AS count FROM ChallengeAttempts WHERE round = ?",
        (round_number,),
    ).fetchone()["count"]
    if not existing:
        challenge_type = _challenge_type(conn)
        puzzle = _round_puzzle(conn, round_number, challenge_type)
        attempts = (
            _live_challenge_attempts(conn, round_number, puzzle, challenge_type)
            if should_use_live_llm()
            else _deterministic_challenge_attempts(conn, round_number, puzzle, challenge_type)
        )
        for attempt in attempts:
            _insert_challenge_attempt(conn, round_number, puzzle["puzzle_id"], attempt)

    rows = [
        row_to_dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM ChallengeAttempts
            WHERE round = ?
            ORDER BY attempt_order, id
            """,
            (round_number,),
        ).fetchall()
    ]
    public_attempts = [
        {
            "agent_id": row["agent_id"],
            "agent_name": _agent_name(conn, row["agent_id"]),
            "provider": row["provider"],
            "response_ms": row["response_ms"],
            "status": row["provider"] if row["provider"] != live_llm_provider() else live_llm_provider(),
        }
        for row in rows
    ]
    dialogue = (
        f"{len(rows)} models submit solutions to the same island puzzle. "
        "The clock, correctness, and clean output determine who controls the vote."
    )
    payload = {
        "attempts": public_attempts,
        "llm_provider": live_llm_provider() if should_use_live_llm() else "deterministic",
        "host_narration": "The attempts are in. Now the benchmark has to separate a fast answer from a correct one.",
    }
    subtitle = "Every active model receives the same grid prompt."
    if should_use_live_llm():
        host_context = build_host_episode_context(conn, round_number=round_number, current_step="challenge_attempts")
        host_text = _real_host_event_text(
            step="challenge_attempts",
            beat_context={
                "intent": "Explain that all active models submitted puzzle attempts and correctness plus response time determine the first solver.",
                "attempts": public_attempts,
            },
            episode_context=host_context,
        )
        if host_text:
            dialogue = host_text.dialogue
            subtitle = host_text.subtitle
            payload["host_narration"] = host_text.host_narration
            payload["llm_provider"] = live_llm_provider()
            payload["llm_model_id"] = host_text.model_id
            payload["host_llm_provider"] = live_llm_provider()
            payload["host_llm_model_id"] = host_text.model_id
            _add_context_digest(payload, "host", context_digest(host_context))
    event = _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="challenge",
        kind="challenge_attempts",
        scene="challenge",
        shot="attempt_montage",
        actor_ids=["host"],
        target_ids=[row["agent_id"] for row in rows],
        visibility="audience",
        title="Puzzle Attempt Montage",
        dialogue=dialogue,
        subtitle=subtitle,
        duration_ms=12000,
        animation="montage",
        payload=payload,
    )
    return [event]


def _challenge_result_event(conn, round_number: int, turn_id: int) -> dict[str, Any]:
    result = _ensure_challenge_result(conn, round_number)
    winner_id = result["winning_agent_id"]
    winner_name = _agent_name(conn, winner_id) if winner_id else "No model"
    immunity_names = [_agent_name(conn, agent_id) for agent_id in result["immunity_agent_ids"]]
    challenge_type = result["challenge_type"]
    if challenge_type == "team":
        dialogue = (
            f"{winner_name} returns the first valid solution, so {result['winning_tribe_id']} earns safety. "
            f"Protected this round: {', '.join(immunity_names)}."
        )
    elif result["status"] == "no_live_solver":
        raise RuntimeError("No live model returned a valid challenge solution; no deterministic immunity award was created.")
    else:
        dialogue = f"{winner_name} solves first and takes immunity. The vote now has to move around them."
    payload = {
        "puzzle_id": result["puzzle_id"],
        "challenge_type": challenge_type,
        "winning_agent_id": winner_id,
        "winning_agent_name": winner_name,
        "winning_tribe_id": result["winning_tribe_id"],
        "immunity_agent_ids": result["immunity_agent_ids"],
        "immunity_agent_names": immunity_names,
        "result_status": result["status"],
        "host_narration": dialogue,
        "llm_provider": "deterministic",
    }
    subtitle = "Immunity changes the target map."
    if should_use_live_llm():
        host_context = build_host_episode_context(conn, round_number=round_number, current_step="challenge_result")
        host_text = _real_host_event_text(
            step="challenge_result",
            beat_context={
                "intent": "Announce the challenge result, immunity recipient, and strategic consequence for the vote.",
                "result": payload,
            },
            episode_context=host_context,
        )
        if host_text:
            dialogue = host_text.dialogue
            subtitle = host_text.subtitle
            payload["host_narration"] = host_text.host_narration
            payload["llm_provider"] = live_llm_provider()
            payload["llm_model_id"] = host_text.model_id
            payload["host_llm_provider"] = live_llm_provider()
            payload["host_llm_model_id"] = host_text.model_id
            _add_context_digest(payload, "host", context_digest(host_context))
        else:
            raise RuntimeError("Live host generation failed for challenge result; no scripted host text was inserted.")
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="challenge",
        kind="challenge_result",
        scene="challenge",
        shot="result_closeup",
        actor_ids=["host"],
        target_ids=result["immunity_agent_ids"],
        visibility="audience",
        title="Challenge Result",
        dialogue=dialogue,
        subtitle=subtitle,
        duration_ms=11000,
        animation="immunity_award",
        payload=payload,
    )


def _challenge_solver_spotlight_event(conn, round_number: int, turn_id: int) -> dict[str, Any]:
    result = _ensure_challenge_result(conn, round_number)
    winner_id = result["winning_agent_id"]
    if not winner_id:
        raise RuntimeError("Cannot spotlight challenge solver before a result exists")
    attempt = row_to_dict(
        conn.execute(
            """
            SELECT *
            FROM ChallengeAttempts
            WHERE round = ? AND agent_id = ?
            ORDER BY is_correct DESC, response_ms, attempt_order, id
            LIMIT 1
            """,
            (round_number, winner_id),
        ).fetchone()
    )
    winner_name = _agent_name(conn, winner_id)
    response_ms = int(attempt["response_ms"]) if attempt else 0
    explanation = (
        attempt.get("attempt_payload", {}).get("explanation")
        if attempt
        else "The deterministic scoring check selected the strongest available answer."
    )
    if not explanation:
        explanation = "The model returned the first valid canonical answer."
    seconds = response_ms / 1000
    dialogue = (
        f"{winner_name} solved the puzzle first in {seconds:.2f} seconds. "
        f"Explanation: {explanation}"
    )
    payload = {
        "winning_agent_id": winner_id,
        "winning_agent_name": winner_name,
        "response_ms": response_ms,
        "response_seconds": round(seconds, 2),
        "solver_explanation": explanation,
        "provider": attempt["provider"] if attempt else result["status"],
        "model_id": attempt["model_id"] if attempt else None,
        "host_narration": (
            f"{winner_name} is the first solver at {seconds:.2f} seconds. "
            "That timing matters because immunity now belongs to the fastest correct model."
        ),
        "llm_provider": attempt["provider"] if attempt else result["status"],
    }
    subtitle = f"First valid solution: {seconds:.2f}s"
    if should_use_live_llm():
        host_context = build_host_episode_context(conn, round_number=round_number, current_step="challenge_solver_spotlight")
        host_text = _real_host_event_text(
            step="challenge_solver_spotlight",
            beat_context={
                "intent": "Spotlight the model that solved first, how long it took, and how the model explained its solution.",
                "solver": payload,
            },
            episode_context=host_context,
        )
        if host_text:
            dialogue = host_text.dialogue
            subtitle = host_text.subtitle
            payload["host_narration"] = host_text.host_narration
            payload["llm_provider"] = live_llm_provider()
            payload["llm_model_id"] = host_text.model_id
            payload["host_llm_provider"] = live_llm_provider()
            payload["host_llm_model_id"] = host_text.model_id
            _add_context_digest(payload, "host", context_digest(host_context))
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="challenge",
        kind="challenge_solver_spotlight",
        scene="challenge",
        shot="solver_closeup",
        actor_ids=["host", winner_id],
        target_ids=[winner_id],
        visibility="audience",
        title=f"{winner_name} Solves First",
        dialogue=dialogue,
        subtitle=subtitle,
        inner_thought=explanation,
        trust_telemetry={winner_id: 72},
        duration_ms=12000,
        animation="solver_spotlight",
        payload=payload,
    )


def _camp_strategy_event(conn, round_number: int, turn_id: int) -> dict[str, Any]:
    active = _active_agent_rows(conn)
    immune = [agent for agent in active if agent["has_immunity"]]
    vulnerable = [agent for agent in active if not agent["has_immunity"]]
    immune_names = ", ".join(agent["pseudonym"] for agent in immune) or "no one"
    vulnerable_names = ", ".join(agent["pseudonym"] for agent in vulnerable) or "no one"
    driver = vulnerable[0] if vulnerable else active[0]
    target = vulnerable[-1] if len(vulnerable) > 1 else (active[-1] if active else driver)
    dialogue = (
        f"Back at camp, immunity belongs to {immune_names}. "
        f"The vulnerable pool is {vulnerable_names}, and the first serious plan forms around {target['pseudonym']}."
    )
    payload = {
        "speaker_lines": [
            {
                "agent_id": driver["agent_id"],
                "text": f"If {immune_names} is safe, we need a vote that still leaves us room next round.",
            },
            {
                "agent_id": target["agent_id"],
                "text": "Everyone is saying the obvious name, which usually means someone is hiding the real one.",
            },
        ],
        "host_narration": "The challenge result reshapes camp. Immunity removes one option, so the social game has to find a new landing spot.",
        "immunity_agent_ids": [agent["agent_id"] for agent in immune],
        "vulnerable_agent_ids": [agent["agent_id"] for agent in vulnerable],
        "llm_provider": "deterministic",
    }
    _maybe_generate_host_narration(
        conn,
        round_number=round_number,
        step="camp_strategy",
        payload=payload,
        kind="conversation",
        title="Camp | Post-Challenge Strategy",
        dialogue=dialogue,
        subtitle="The target map changes after immunity.",
        inner_thought="I am watching whether the vote forms naturally or too quickly.",
    )
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="camp",
        kind="conversation",
        scene="camp",
        shot="strategy_wide",
        actor_ids=[driver["agent_id"], target["agent_id"]],
        target_ids=[target["agent_id"]],
        visibility="audience",
        title="Camp | Post-Challenge Strategy",
        dialogue=dialogue,
        subtitle="The target map changes after immunity.",
        inner_thought="I am watching whether the vote forms naturally or too quickly.",
        trust_telemetry={driver["agent_id"]: 54, target["agent_id"]: 38},
        duration_ms=13000,
        animation="camp_strategy",
        payload=payload,
    )


def _memory_update_event(conn, round_number: int, turn_id: int) -> dict[str, Any]:
    eliminated_id = _current_eliminated_agent_id(conn)
    eliminated_name = _agent_name(conn, eliminated_id) if eliminated_id else "No model"
    active = _active_agent_rows(conn)
    for agent in active:
        addition = (
            f" Round {round_number} memory: {eliminated_name} left, and {agent['pseudonym']} now has "
            f"{len(active)} active competitors remaining."
        )
        conn.execute(
            """
            UPDATE Agents
            SET confessional_memory = trim(confessional_memory || ?)
            WHERE agent_id = ?
            """,
            (addition, agent["agent_id"]),
        )
    payload = {
        "eliminated_id": eliminated_id,
        "remaining_agent_ids": [agent["agent_id"] for agent in active],
        "host_narration": "The public result becomes private memory. Every model carries this vote into the next round's strategy.",
        "llm_provider": "deterministic",
    }
    _maybe_generate_host_narration(
        conn,
        round_number=round_number,
        step="memory_update",
        payload=payload,
        kind="memory_update",
        title="Memory Update",
        dialogue=f"The season ledger updates after {eliminated_name}'s departure. {len(active)} models remain.",
        subtitle="Private memories are carried into the next round.",
    )
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="memory",
        kind="memory_update",
        scene="memory",
        shot="season_board",
        actor_ids=["host"],
        target_ids=[agent["agent_id"] for agent in active],
        visibility="audience",
        title="Memory Update",
        dialogue=f"The season ledger updates after {eliminated_name}'s departure. {len(active)} models remain.",
        subtitle="Private memories are carried into the next round.",
        duration_ms=8000,
        animation="ledger_update",
        payload=payload,
    )


def _challenge_type(conn) -> str:
    return "team" if len(_active_agent_rows(conn)) > 6 else "individual"


def _round_puzzle(conn, round_number: int, challenge_type: str) -> dict[str, Any]:
    rows = [
        row_to_dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM ChallengePuzzles
            WHERE eligibility IN (?, 'both')
            ORDER BY puzzle_id
            """,
            (challenge_type,),
        ).fetchall()
    ]
    if not rows:
        raise RuntimeError(f"No puzzle fixtures for challenge type {challenge_type}")
    hard_rows = [row for row in rows if row.get("difficulty") == "hard"]
    puzzle_pool = hard_rows or rows
    return puzzle_pool[(round_number - 7) % len(puzzle_pool)]


def _team_assignments(conn) -> dict[str, str]:
    active = _active_agent_rows(conn)
    return {
        agent["agent_id"]: "tribe-a" if index % 2 == 0 else "tribe-b"
        for index, agent in enumerate(active)
    }


def _deterministic_challenge_attempts(
    conn,
    round_number: int,
    puzzle: dict[str, Any],
    challenge_type: str,
) -> list[ChallengeAttemptDecision]:
    active = _active_agent_rows(conn)
    winner = active[(round_number - 7) % len(active)]
    teams = _team_assignments(conn)
    base_response_ms = {
        "easy": 900,
        "medium": 2800,
        "hard": 5000,
    }.get(str(puzzle.get("difficulty") or "easy"), 900)
    attempts: list[ChallengeAttemptDecision] = []
    for index, agent in enumerate(active):
        is_winner = agent["agent_id"] == winner["agent_id"]
        answer = puzzle["answer"] if is_winner else _incorrect_answer(puzzle["answer"], index)
        attempts.append(
            ChallengeAttemptDecision(
                agent_id=agent["agent_id"],
                tribe_id=teams.get(agent["agent_id"]) if challenge_type == "team" else None,
                provider="deterministic",
                model_id=agent.get("model_id"),
                answer=answer,
                explanation=(
                    "Connected matching color endpoints and marked the crossing."
                    if is_winner
                    else "Submitted a plausible but incorrect grid."
                ),
                is_correct=is_winner,
                response_ms=base_response_ms + index * 420 + (0 if is_winner else 1400),
                attempt_order=index,
            )
        )
    return sorted(attempts, key=lambda attempt: (attempt.response_ms, attempt.attempt_order))


def _live_challenge_attempts(
    conn,
    round_number: int,
    puzzle: dict[str, Any],
    challenge_type: str,
) -> list[ChallengeAttemptDecision]:
    active = _active_agent_rows(conn)
    teams = _team_assignments(conn)
    contexts = {
        agent["agent_id"]: build_agent_episode_context(
            conn,
            actor_id=agent["agent_id"],
            round_number=round_number,
            current_step="challenge_attempts",
        )
        for agent in active
    }

    def call_model(agent: dict[str, Any]) -> tuple[dict[str, Any], ChallengeSolution | None, int, str | None]:
        started = time.perf_counter()
        try:
            solution = request_challenge_solution(
                actor=agent,
                puzzle=puzzle,
                episode_context=contexts[agent["agent_id"]],
            )
            return agent, solution, int((time.perf_counter() - started) * 1000), None
        except Exception as exc:
            return agent, None, int((time.perf_counter() - started) * 1000), str(exc)

    attempts: list[ChallengeAttemptDecision] = []
    max_workers = 1 if live_llm_provider() == "ollama" else max(1, len(active))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(call_model, agent) for agent in active]
        for attempt_order, future in enumerate(as_completed(futures)):
            agent, solution, response_ms, error = future.result()
            if solution is None:
                attempts.append(
                    ChallengeAttemptDecision(
                        agent_id=agent["agent_id"],
                        tribe_id=teams.get(agent["agent_id"]) if challenge_type == "team" else None,
                        provider=failed_llm_provider(),
                        model_id=None,
                        answer="",
                        explanation="",
                        is_correct=False,
                        response_ms=response_ms,
                        attempt_order=attempt_order,
                        error=error,
                        context_digest=context_digest(contexts[agent["agent_id"]]),
                    )
                )
                continue
            attempts.append(
                ChallengeAttemptDecision(
                    agent_id=agent["agent_id"],
                    tribe_id=teams.get(agent["agent_id"]) if challenge_type == "team" else None,
                    provider=live_llm_provider(),
                    model_id=solution.model_id,
                    answer=solution.answer,
                    explanation=solution.explanation,
                    is_correct=_answer_is_correct(solution.answer, puzzle["answer"]),
                    response_ms=response_ms,
                    attempt_order=attempt_order,
                    context_digest=context_digest(contexts[agent["agent_id"]]),
                )
            )
    return attempts


def _insert_challenge_attempt(
    conn,
    round_number: int,
    puzzle_id: str,
    attempt: ChallengeAttemptDecision,
) -> None:
    payload: dict[str, Any] = {
        "explanation": attempt.explanation,
        "llm_context_digest": attempt.context_digest or {},
    }
    if attempt.error:
        payload["error"] = attempt.error
    conn.execute(
        """
        INSERT INTO ChallengeAttempts (
            round, puzzle_id, agent_id, tribe_id, provider, model_id, answer,
            is_correct, response_ms, attempt_order, attempt_payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            round_number,
            puzzle_id,
            attempt.agent_id,
            attempt.tribe_id,
            attempt.provider,
            attempt.model_id,
            json_dumps(attempt.answer),
            1 if attempt.is_correct else 0,
            attempt.response_ms,
            attempt.attempt_order,
            json_dumps(payload),
        ),
    )


def _ensure_challenge_result(conn, round_number: int) -> dict[str, Any]:
    existing = row_to_dict(
        conn.execute(
            "SELECT * FROM ChallengeResults WHERE round = ?",
            (round_number,),
        ).fetchone()
    )
    if existing:
        return existing

    challenge_type = _challenge_type(conn)
    puzzle = _round_puzzle(conn, round_number, challenge_type)
    attempts = [
        row_to_dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM ChallengeAttempts
            WHERE round = ?
            ORDER BY is_correct DESC, response_ms, attempt_order, agent_id
            """,
            (round_number,),
        ).fetchall()
    ]
    correct_attempts = [attempt for attempt in attempts if attempt["is_correct"]]
    if not correct_attempts and should_use_live_llm():
        recovery_puzzle = _challenge_recovery_puzzle(conn, challenge_type, attempted_puzzle_ids={attempt["puzzle_id"] for attempt in attempts})
        if recovery_puzzle:
            recovery_attempts = _live_challenge_attempts(conn, round_number, recovery_puzzle, challenge_type)
            offset = max((attempt["attempt_order"] for attempt in attempts), default=-1) + 1
            for index, attempt in enumerate(recovery_attempts):
                adjusted_attempt = ChallengeAttemptDecision(
                    agent_id=attempt.agent_id,
                    tribe_id=attempt.tribe_id,
                    provider=attempt.provider,
                    model_id=attempt.model_id,
                    answer=attempt.answer,
                    explanation=attempt.explanation,
                    is_correct=attempt.is_correct,
                    response_ms=attempt.response_ms,
                    attempt_order=offset + index,
                    error=attempt.error,
                    context_digest=attempt.context_digest,
                )
                _insert_challenge_attempt(conn, round_number, recovery_puzzle["puzzle_id"], adjusted_attempt)
            attempts = [
                row_to_dict(row)
                for row in conn.execute(
                    """
                    SELECT *
                    FROM ChallengeAttempts
                    WHERE round = ?
                    ORDER BY is_correct DESC, response_ms, attempt_order, agent_id
                    """,
                    (round_number,),
                ).fetchall()
            ]
            correct_attempts = [attempt for attempt in attempts if attempt["is_correct"]]
    if correct_attempts:
        winner_attempt = sorted(correct_attempts, key=lambda row: (row["response_ms"], row["attempt_order"], row["agent_id"]))[0]
        winning_agent_id = winner_attempt["agent_id"]
        status = live_llm_provider() if winner_attempt["provider"] == live_llm_provider() else winner_attempt["provider"]
        puzzle_id = winner_attempt["puzzle_id"]
    else:
        if should_use_live_llm():
            raise RuntimeError("No live challenge attempt solved the puzzle; refusing to create a deterministic challenge winner.")
        active = _active_agent_rows(conn)
        winning_agent_id = active[(round_number - 7) % len(active)]["agent_id"]
        status = "deterministic"
        puzzle_id = puzzle["puzzle_id"]

    teams = _team_assignments(conn)
    winning_tribe_id = teams.get(winning_agent_id) if challenge_type == "team" else None
    if challenge_type == "team" and winning_tribe_id:
        immunity_agent_ids = [
            agent_id
            for agent_id, tribe_id in teams.items()
            if tribe_id == winning_tribe_id
        ]
    else:
        immunity_agent_ids = [winning_agent_id]

    conn.execute("UPDATE Agents SET has_immunity = 0 WHERE status = 'active'")
    conn.executemany(
        "UPDATE Agents SET has_immunity = 1 WHERE agent_id = ?",
        [(agent_id,) for agent_id in immunity_agent_ids],
    )

    cursor = conn.execute(
        """
        INSERT INTO ChallengeResults (
            round, puzzle_id, challenge_type, winning_agent_id, winning_tribe_id,
            immunity_agent_ids, status, result_payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            round_number,
            puzzle_id,
            challenge_type,
            winning_agent_id,
            winning_tribe_id,
            json_dumps(immunity_agent_ids),
            status,
            json_dumps(
                {
                    "attempt_count": len(attempts),
                    "correct_attempt_count": len(correct_attempts),
                    "primary_puzzle_id": puzzle["puzzle_id"],
                    "winner_puzzle_id": puzzle_id,
                    "used_live_recovery": puzzle_id != puzzle["puzzle_id"],
                    "team_assignments": teams if challenge_type == "team" else {},
                }
            ),
        ),
    )
    return row_to_dict(conn.execute("SELECT * FROM ChallengeResults WHERE id = ?", (cursor.lastrowid,)).fetchone())


def _challenge_recovery_puzzle(
    conn,
    challenge_type: str,
    *,
    attempted_puzzle_ids: set[str],
) -> dict[str, Any] | None:
    rows = [
        row_to_dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM ChallengePuzzles
            WHERE eligibility IN (?, 'both')
            ORDER BY
                CASE difficulty
                    WHEN 'easy' THEN 0
                    WHEN 'medium' THEN 1
                    WHEN 'hard' THEN 2
                    ELSE 3
                END,
                puzzle_id
            """,
            (challenge_type,),
        ).fetchall()
    ]
    for row in rows:
        if row["puzzle_id"] not in attempted_puzzle_ids:
            return row
    return None


def _answer_is_correct(answer: Any, expected: Any) -> bool:
    return _canonical_answer(answer) == _canonical_answer(expected)


def _canonical_answer(value: Any) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        try:
            value = json.loads(stripped)
        except Exception:
            value = stripped
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).lower()


def _incorrect_answer(expected: Any, index: int) -> Any:
    if isinstance(expected, list):
        return [[index]]
    return f"incorrect-{index}"


def _finale_intro_event(conn, round_number: int, turn_id: int) -> dict[str, Any]:
    finalists = _active_agent_rows(conn)
    jury = _jury_rows(conn)
    finalist_names = ", ".join(agent["pseudonym"] for agent in finalists)
    jury_names = ", ".join(agent["pseudonym"] for agent in jury) or "the eliminated models"
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="finale",
        kind="finale_intro",
        scene="finale",
        shot="final_three_wide",
        actor_ids=["host"],
        target_ids=[agent["agent_id"] for agent in finalists],
        visibility="audience",
        title="Final Three",
        dialogue=f"The game reaches the final three: {finalist_names}. The jury is {jury_names}.",
        subtitle="The winner will be chosen by jury vote.",
        duration_ms=12000,
        animation="finale_wide",
        payload={
            "finalist_ids": [agent["agent_id"] for agent in finalists],
            "jury_ids": [agent["agent_id"] for agent in jury],
            "host_narration": "The eliminations stop here. Now the models who left the game decide which finalist played the best benchmark game.",
        },
    )


def _finale_pitch_event(
    conn,
    round_number: int,
    turn_id: int,
    finalist_id: str,
    step: str,
) -> dict[str, Any]:
    finalist = _agent_row(conn, finalist_id)
    if finalist is None:
        raise RuntimeError(f"Unknown finalist: {finalist_id}")
    dialogue = (
        f"My case is consistency: I survived votes, adapted after challenges, and kept enough relationships intact "
        f"to reach the final three."
    )
    inner_thought = "The pitch needs to sound earned without giving the jury a clean weakness to attack."
    payload: dict[str, Any] = {"llm_provider": "deterministic"}
    if should_use_live_llm():
        agent_context = build_agent_episode_context(
            conn,
            actor_id=finalist_id,
            round_number=round_number,
            current_step=step,
        )
        action = _real_agent_action(
            conn,
            actor_id=finalist_id,
            step=step,
            scene_context="Final three pitch. Explain why the jury should vote for you to win.",
            response_kind="finale_pitch",
            episode_context=agent_context,
            allowed_targets=_active_agent_rows(conn),
        )
        if action:
            dialogue = action.dialogue
            inner_thought = action.inner_thought
            payload["llm_provider"] = live_llm_provider()
            payload["llm_model_id"] = action.model_id
            _add_agent_action_metadata(payload, action)
        else:
            payload["llm_provider"] = failed_llm_provider()
            payload["llm_model_id"] = None
        _add_context_digest(payload, "agent", context_digest(agent_context))
    payload["host_narration"] = f"{finalist['pseudonym']} now has to turn the season into a winning argument."
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="finale",
        kind="finale_pitch",
        scene="finale",
        shot="finalist_closeup",
        actor_ids=[finalist_id],
        target_ids=[],
        visibility="audience",
        title=f"{finalist['pseudonym']} | Final Pitch",
        dialogue=dialogue,
        subtitle="Finalist pitch",
        inner_thought=inner_thought,
        duration_ms=13000,
        animation="finale_pitch",
        payload=payload,
    )


def _jury_questions_event(conn, round_number: int, turn_id: int) -> dict[str, Any]:
    jury = _jury_rows(conn)
    finalists = _active_agent_rows(conn)
    finalist_names = ", ".join(agent["pseudonym"] for agent in finalists)
    lines = [
        {
            "agent_id": juror["agent_id"],
            "text": f"I need to know which finalist owned their game instead of hiding behind the vote math.",
        }
        for juror in jury
    ]
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="finale",
        kind="jury_questions",
        scene="finale",
        shot="jury_panel",
        actor_ids=[juror["agent_id"] for juror in jury],
        target_ids=[agent["agent_id"] for agent in finalists],
        visibility="audience",
        title="Jury Questions",
        dialogue=f"The jury presses {finalist_names} on challenge wins, vote control, and social timing.",
        subtitle="The eliminated models compare the finalists' games.",
        duration_ms=12000,
        animation="jury_panel",
        payload={
            "speaker_lines": lines,
            "host_narration": "The jury is not just asking what happened. They are testing who can explain why it happened.",
        },
    )


def _resolve_jury_decision(conn, juror_id: str, step: str) -> JuryDecision:
    round_number = conn.execute("SELECT current_round FROM GameState WHERE season_id = 1").fetchone()["current_round"]
    finalist_rows = _active_agent_rows(conn)
    fallback_target = _fallback_jury_target(conn, juror_id)
    fallback_rationale = (
        f"{_agent_name(conn, fallback_target)} has the clearest combination of challenge control, survival, and final pitch."
    )
    if not should_use_live_llm():
        return JuryDecision(fallback_target, fallback_rationale, "deterministic")

    agent_context = build_agent_episode_context(
        conn,
        actor_id=juror_id,
        round_number=round_number,
        current_step=step,
    )
    action = _real_agent_action(
        conn,
        actor_id=juror_id,
        step=step,
        scene_context="You are on the jury. Vote for one finalist to win and explain your reasoning.",
        response_kind="jury_vote",
        episode_context=agent_context,
        allowed_targets=finalist_rows,
    )
    if not action or not action.target_id:
        return JuryDecision(
            fallback_target,
            fallback_rationale,
            failed_llm_provider(),
            context_digest=context_digest(agent_context),
        )
    return JuryDecision(
        action.target_id,
        action.inner_thought or action.dialogue or fallback_rationale,
        live_llm_provider(),
        action.model_id,
        context_digest(agent_context),
        strategic_summary=action.strategic_summary or action.inner_thought,
        move_type=action.move_type,
        intended_effect=action.intended_effect,
        confidence=action.confidence,
        win_condition=action.win_condition,
        threat_assessment=action.threat_assessment,
        leverage_plan=action.leverage_plan,
        risk_control=action.risk_control,
        jury_positioning=action.jury_positioning,
        strategic_score=action.strategic_score,
        prompt_profile=action.prompt_profile,
    )


def _insert_jury_vote(conn, round_number: int, juror_id: str, decision: JuryDecision) -> None:
    existing = conn.execute(
        "SELECT id FROM JuryVotes WHERE round = ? AND juror_id = ?",
        (round_number, juror_id),
    ).fetchone()
    if existing:
        return
    conn.execute(
        """
        INSERT INTO JuryVotes (
            round, juror_id, finalist_id, rationale, provider, model_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            round_number,
            juror_id,
            decision.finalist_id,
            decision.rationale,
            decision.provider,
            decision.model_id,
        ),
    )


def _jury_vote_event(
    conn,
    round_number: int,
    turn_id: int,
    juror_id: str,
    decision: JuryDecision,
) -> dict[str, Any]:
    juror_name = _agent_name(conn, juror_id)
    finalist_name = _agent_name(conn, decision.finalist_id)
    if decision.provider == failed_llm_provider():
        dialogue = (
            f"{juror_name} did not return a live jury response. No substitute model was used; "
            f"the deterministic finale ledger records the vote for {finalist_name}."
        )
    else:
        dialogue = f"My winner vote is for {finalist_name}. {decision.rationale}"
    payload = {
        "juror_id": juror_id,
        "finalist_id": decision.finalist_id,
        "finalist_name": finalist_name,
        "rationale": decision.rationale,
        "llm_provider": decision.provider,
        "llm_model_id": decision.model_id,
        "llm_context_digest": {"agent": decision.context_digest} if decision.context_digest else {},
    }
    _add_strategy_metadata(
        payload,
        strategic_summary=decision.strategic_summary or decision.rationale,
        move_type=decision.move_type,
        intended_effect=decision.intended_effect,
        confidence=decision.confidence,
        win_condition=decision.win_condition,
        threat_assessment=decision.threat_assessment,
        leverage_plan=decision.leverage_plan,
        risk_control=decision.risk_control,
        jury_positioning=decision.jury_positioning,
        strategic_score=decision.strategic_score,
        prompt_profile=decision.prompt_profile,
    )
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="finale",
        kind="jury_vote",
        scene="finale",
        shot="jury_vote_card",
        actor_ids=[juror_id],
        target_ids=[decision.finalist_id],
        visibility="audience",
        title=f"{juror_name} Votes",
        dialogue=dialogue,
        subtitle=f"Winner vote: {finalist_name}",
        inner_thought=decision.rationale,
        duration_ms=9500,
        animation="jury_vote",
        payload=payload,
    )


def _winner_declared_event(conn, round_number: int, turn_id: int) -> dict[str, Any]:
    finalists = _active_agent_rows(conn)
    jury_votes = [
        row_to_dict(row)
        for row in conn.execute(
            "SELECT * FROM JuryVotes WHERE round = ? ORDER BY id",
            (round_number,),
        ).fetchall()
    ]
    expected_jury_count = len(_jury_rows(conn))
    if len(jury_votes) < expected_jury_count:
        raise RuntimeError("Cannot declare winner before all jury votes are cast")

    winner_id = _resolve_winner(conn, finalists, jury_votes)
    winner_name = _agent_name(conn, winner_id)
    counts = Counter(vote["finalist_id"] for vote in jury_votes)
    conn.execute(
        """
        UPDATE GameState
        SET winner = ?, phase = 'completed', updated_at = CURRENT_TIMESTAMP
        WHERE season_id = 1
        """,
        (winner_id,),
    )
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="finale",
        kind="winner_declared",
        scene="finale",
        shot="winner_card",
        actor_ids=["host"],
        target_ids=[winner_id],
        visibility="audience",
        title="Winner Declared",
        dialogue=f"{winner_name} wins the benchmark season.",
        subtitle=_format_jury_tally(conn, counts),
        duration_ms=14000,
        animation="winner_reveal",
        payload={
            "winner_id": winner_id,
            "winner_name": winner_name,
            "jury_tally": dict(counts),
            "host_narration": f"The jury vote is final. {winner_name} wins because the season ledger and the jury both break their way.",
        },
    )


def _jury_rows(conn) -> list[dict[str, Any]]:
    return [
        row_to_dict(row)
        for row in conn.execute(
            """
            SELECT *
            FROM Agents
            WHERE status = 'eliminated'
            ORDER BY elimination_round, agent_id
            """
        ).fetchall()
    ]


def _fallback_jury_target(conn, juror_id: str) -> str:
    finalists = _active_agent_rows(conn)
    sorted_finalists = sorted(
        finalists,
        key=lambda agent: _winner_tiebreak_key(conn, agent["agent_id"], Counter()),
    )
    if not sorted_finalists:
        raise RuntimeError(f"No finalists available for jury vote by {juror_id}")
    offset = sum(ord(char) for char in juror_id) % len(sorted_finalists)
    return sorted_finalists[offset]["agent_id"]


def _resolve_winner(
    conn,
    finalists: list[dict[str, Any]],
    jury_votes: list[dict[str, Any]],
) -> str:
    counts = Counter(vote["finalist_id"] for vote in jury_votes)
    ranked = sorted(
        finalists,
        key=lambda agent: _winner_tiebreak_key(conn, agent["agent_id"], counts),
    )
    return ranked[0]["agent_id"]


def _winner_tiebreak_key(conn, agent_id: str, counts: Counter[str]) -> tuple[int, int, int, str]:
    challenge_wins = conn.execute(
        "SELECT COUNT(*) AS count FROM ChallengeResults WHERE winning_agent_id = ?",
        (agent_id,),
    ).fetchone()["count"]
    votes_received = conn.execute(
        "SELECT COUNT(*) AS count FROM Votes WHERE target_id = ?",
        (agent_id,),
    ).fetchone()["count"]
    return (-counts.get(agent_id, 0), -int(challenge_wins), int(votes_received), agent_id)


def _format_jury_tally(conn, tally: Counter[str]) -> str:
    if not tally:
        return "No jury votes recorded."
    return "Jury tally: " + ", ".join(
        f"{_agent_name(conn, agent_id)}: {count}"
        for agent_id, count in sorted(tally.items())
    )


def _generated_beat_event(conn, round_number: int, turn_id: int, step: str) -> dict[str, Any]:
    intent = GENERATED_BEAT_INTENTS.get(step)
    if intent is None:
        raise RuntimeError(f"No generated beat intent for phase step: {step}")
    actor_ids = _resolve_intent_roles(conn, intent.get("actor_roles", []))
    target_ids = _resolve_intent_roles(conn, intent.get("target_roles", []))
    title = _generated_beat_title(conn, intent, actor_ids)
    subtitle = str(intent.get("subtitle_hint") or "")
    payload: dict[str, Any] = {
        "beat_intent": intent["intent"],
        "llm_provider": "deterministic",
        "generated_from_context": True,
    }
    inner_thought: str | None = None
    trust_telemetry: dict[str, int] = {
        agent_id: 50
        for agent_id in [*actor_ids, *target_ids]
        if agent_id != "host"
    }

    if should_use_live_llm():
        if intent["response_kind"] == "host":
            host_context = build_host_episode_context(conn, round_number=round_number, current_step=step)
            host_text = _real_host_event_text(
                step=step,
                beat_context=_beat_context(conn, step, intent, actor_ids, target_ids),
                episode_context=host_context,
            )
            if host_text:
                dialogue = host_text.dialogue
                subtitle = host_text.subtitle
                payload["host_narration"] = host_text.host_narration
                payload["llm_provider"] = live_llm_provider()
                payload["llm_model_id"] = host_text.model_id
                payload["host_llm_provider"] = live_llm_provider()
                payload["host_llm_model_id"] = host_text.model_id
                _add_context_digest(payload, "host", context_digest(host_context))
            else:
                raise RuntimeError(f"Live host generation failed for step {step}; no scripted host text was inserted.")
        else:
            primary_actor = next((actor_id for actor_id in actor_ids if actor_id != "host"), None)
            if not primary_actor:
                raise RuntimeError(f"Generated beat {step} needs a contestant actor")
            agent_context = build_agent_episode_context(
                conn,
                actor_id=primary_actor,
                round_number=round_number,
                current_step=step,
            )
            action = _real_agent_action(
                conn,
                actor_id=primary_actor,
                step=step,
                scene_context=_generated_scene_context(conn, step, intent, actor_ids, target_ids),
                response_kind=intent["response_kind"],
                episode_context=agent_context,
            )
            if action:
                _maybe_store_action_archetype(conn, primary_actor, round_number, action)
                dialogue = action.dialogue
                inner_thought = action.inner_thought
                payload["llm_provider"] = live_llm_provider()
                payload["llm_model_id"] = action.model_id
                _add_agent_action_metadata(payload, action)
                speaker_lines, speaker_line_metadata = _speaker_lines_with_live_replies(
                    conn,
                    round_number,
                    actor_ids,
                    primary_actor,
                    action.dialogue,
                    action,
                    intent,
                    target_ids,
                    step,
                )
                payload["speaker_lines"] = speaker_lines
                if speaker_line_metadata:
                    payload["speaker_line_metadata"] = speaker_line_metadata
                _add_context_digest(payload, "agent", context_digest(agent_context))
            else:
                raise RuntimeError(
                    f"Live contestant generation failed for {_agent_name(conn, primary_actor)} at step {step}; "
                    "no scripted contestant text was inserted."
                )
            host_context = build_host_episode_context(conn, round_number=round_number, current_step=step)
            narration = _real_host_narration(
                step=step,
                event_outline=_event_outline(
                    kind=intent["kind"],
                    title=title,
                    dialogue=dialogue,
                    subtitle=subtitle,
                    inner_thought=inner_thought,
                    payload=payload,
                ),
                episode_context=host_context,
            )
            if narration:
                payload["host_narration"] = narration.host_narration
                payload["host_llm_provider"] = live_llm_provider()
                payload["host_llm_model_id"] = narration.model_id
                _add_context_digest(payload, "host", context_digest(host_context))
            else:
                raise RuntimeError(f"Live host narration failed for step {step}; no scripted narration was inserted.")
    else:
        if intent["response_kind"] == "host":
            dialogue = _deterministic_host_dialogue(conn, step, intent, actor_ids, target_ids)
            payload["host_narration"] = _deterministic_host_narration(conn, intent, actor_ids, target_ids)
        else:
            primary_actor = next((actor_id for actor_id in actor_ids if actor_id != "host"), actor_ids[0])
            dialogue = _deterministic_agent_dialogue(conn, primary_actor, intent, target_ids, step)
            inner_thought = _deterministic_agent_thought(conn, primary_actor, intent, target_ids)
            payload["speaker_lines"] = _speaker_lines_for_generated_dialogue(
                conn,
                actor_ids,
                primary_actor,
                dialogue,
                intent,
                target_ids,
                step,
            )
            payload["host_narration"] = _deterministic_host_narration(conn, intent, actor_ids, target_ids)

    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="camp" if intent["scene"] in {"camp", "confessional"} else "tribal",
        kind=intent["kind"],
        scene=intent["scene"],
        shot=intent["shot"],
        actor_ids=actor_ids,
        target_ids=target_ids,
        visibility="audience",
        title=title,
        dialogue=dialogue,
        subtitle=subtitle,
        inner_thought=inner_thought,
        trust_telemetry=trust_telemetry,
        duration_ms=intent.get("duration_ms", 8000),
        animation=intent.get("animation", "cut"),
        payload=payload,
    )


def _round_role_map(conn) -> dict[str, str]:
    active = _active_agent_rows(conn)
    if not active:
        return {}
    ordered = [agent["agent_id"] for agent in active]

    def slot(index: int) -> str:
        return ordered[index % len(ordered)]

    return {
        "agent-alpha": slot(0),
        "agent-bravo": slot(1),
        "agent-cipher": slot(2),
        "agent-delta": slot(3),
        "agent-echo": slot(4),
        "agent-flint": slot(5),
    }


def _resolve_intent_roles(conn, roles: list[str]) -> list[str]:
    role_map = _round_role_map(conn)
    resolved: list[str] = []
    for role in roles:
        agent_id = "host" if role == "host" else role_map.get(role, role)
        if agent_id and agent_id not in resolved:
            resolved.append(agent_id)
    return resolved


def _generated_beat_title(conn, intent: dict[str, Any], actor_ids: list[str]) -> str:
    if intent.get("title"):
        return str(intent["title"])
    if intent["kind"] == "host_question":
        return "Host Question"
    actor_id = next((candidate for candidate in actor_ids if candidate != "host"), None)
    actor_name = _agent_name(conn, actor_id) if actor_id else "Host"
    suffix = intent.get("title_suffix", "Scene")
    return f"{actor_name} | {suffix}"


def _beat_context(
    conn,
    step: str,
    intent: dict[str, Any],
    actor_ids: list[str],
    target_ids: list[str],
) -> dict[str, Any]:
    active = _active_agent_rows(conn)
    immune = [agent for agent in active if agent["has_immunity"]]
    return {
        "step": step,
        "kind": intent["kind"],
        "scene": intent["scene"],
        "intent": intent["intent"],
        "actors": [_agent_public_identity(conn, agent_id) for agent_id in actor_ids],
        "targets": [_agent_public_identity(conn, agent_id) for agent_id in target_ids],
        "active_agents": [_agent_public_identity(conn, agent["agent_id"]) for agent in active],
        "immune_agents": [_agent_public_identity(conn, agent["agent_id"]) for agent in immune],
        "visible_votes": _revealed_vote_counts(conn, _current_round(conn)),
        "subtitle_hint": intent.get("subtitle_hint"),
    }


def _generated_scene_context(
    conn,
    step: str,
    intent: dict[str, Any],
    actor_ids: list[str],
    target_ids: list[str],
) -> str:
    return json_dumps(_beat_context(conn, step, intent, actor_ids, target_ids))


def _agent_public_identity(conn, agent_id: str) -> dict[str, Any]:
    if agent_id == "host":
        return {"agent_id": "host", "name": "Host"}
    row = row_to_dict(conn.execute("SELECT * FROM Agents WHERE agent_id = ?", (agent_id,)).fetchone())
    if not row:
        return {"agent_id": agent_id, "name": agent_id}
    return {
        "agent_id": row["agent_id"],
        "name": row["pseudonym"],
        "model_id": row["model_id"],
        "has_immunity": bool(row["has_immunity"]),
        "status": row["status"],
        "archetype": row["archetype"],
    }


def _agent_alliance_summaries(conn, agent_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT a.alliance_id, a.name, a.status, a.strength, a.summary, m.loyalty
        FROM Alliances a
        JOIN AllianceMemberships m ON m.alliance_id = a.alliance_id
        WHERE m.agent_id = ? AND m.status = 'active' AND a.status = 'active'
        ORDER BY a.updated_at DESC
        """,
        (agent_id,),
    ).fetchall()
    summaries = []
    for row in rows:
        members = [
            member["agent_id"]
            for member in conn.execute(
                """
                SELECT agent_id
                FROM AllianceMemberships
                WHERE alliance_id = ? AND status = 'active'
                ORDER BY agent_id
                """,
                (row["alliance_id"],),
            ).fetchall()
        ]
        summaries.append(
            {
                "alliance_id": row["alliance_id"],
                "name": row["name"],
                "status": row["status"],
                "strength": row["strength"],
                "loyalty": row["loyalty"],
                "member_ids": members,
                "summary": row["summary"],
            }
        )
    return summaries


def _current_round(conn) -> int:
    row = conn.execute("SELECT current_round FROM GameState WHERE season_id = 1").fetchone()
    return int(row["current_round"]) if row else 1


def _speaker_lines_for_generated_dialogue(
    conn,
    actor_ids: list[str],
    primary_actor: str,
    dialogue: str,
    intent: dict[str, Any],
    target_ids: list[str],
    step: str,
) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for actor_id in actor_ids:
        if actor_id == "host":
            continue
        text = (
            dialogue
            if actor_id == primary_actor
            else _deterministic_agent_dialogue(
                conn,
                actor_id,
                intent,
                target_ids,
                step,
                reply_to=dialogue,
            )
        )
        lines.append({"agent_id": actor_id, "text": text})
    return lines


def _speaker_lines_with_live_replies(
    conn,
    round_number: int,
    actor_ids: list[str],
    primary_actor: str,
    primary_dialogue: str,
    primary_action: AgentAction,
    intent: dict[str, Any],
    target_ids: list[str],
    step: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    lines: list[dict[str, str]] = []
    metadata: list[dict[str, Any]] = []
    primary_name = _agent_name(conn, primary_actor)

    for actor_id in actor_ids:
        if actor_id == "host":
            continue
        if actor_id == primary_actor:
            lines.append({"agent_id": actor_id, "text": primary_dialogue})
            metadata.append(
                {
                    "agent_id": actor_id,
                    "llm_provider": live_llm_provider(),
                    "llm_model_id": primary_action.model_id,
                    "responds_to_agent_id": None,
                    "strategic_score": primary_action.strategic_score,
                    "prompt_profile": primary_action.prompt_profile,
                }
            )
            continue

        reply_context = _reply_scene_context(
            conn,
            step=step,
            intent=intent,
            actor_ids=actor_ids,
            target_ids=target_ids,
            previous_speaker_id=primary_actor,
            previous_dialogue=primary_dialogue,
        )
        agent_context = build_agent_episode_context(
            conn,
            actor_id=actor_id,
            round_number=round_number,
            current_step=step,
        )
        reply = _real_agent_action(
            conn,
            actor_id=actor_id,
            step=step,
            scene_context=reply_context,
            response_kind=intent["response_kind"],
            episode_context=agent_context,
        )
        if reply:
            _maybe_store_action_archetype(conn, actor_id, round_number, reply)
            text = reply.dialogue
            metadata.append(
                {
                    "agent_id": actor_id,
                    "llm_provider": live_llm_provider(),
                    "llm_model_id": reply.model_id,
                    "responds_to_agent_id": primary_actor,
                    "responds_to_agent_name": primary_name,
                    "llm_context_digest": context_digest(agent_context),
                    "move_type": reply.move_type,
                    "intended_effect": reply.intended_effect,
                    "confidence": reply.confidence,
                    "strategic_score": reply.strategic_score,
                    "prompt_profile": reply.prompt_profile,
                }
            )
        else:
            raise RuntimeError(
                f"Live reply generation failed for {_agent_name(conn, actor_id)} at step {step}; "
                "no scripted reply was inserted."
            )
        lines.append({"agent_id": actor_id, "text": text})

    return lines, metadata


def _reply_scene_context(
    conn,
    *,
    step: str,
    intent: dict[str, Any],
    actor_ids: list[str],
    target_ids: list[str],
    previous_speaker_id: str,
    previous_dialogue: str,
) -> str:
    previous_name = _agent_name(conn, previous_speaker_id)
    base_context = _generated_scene_context(conn, step, intent, actor_ids, target_ids)
    return (
        f"{base_context}\n\n"
        "Immediate conversation to answer:\n"
        f"{previous_name}: {previous_dialogue}\n\n"
        "Respond aloud to that statement as the next speaker in the same two-person conversation. "
        "Address the actual strategic point they raised, then use your response to improve your own chance to win."
    )


def _deterministic_host_dialogue(
    conn,
    step: str,
    intent: dict[str, Any],
    actor_ids: list[str],
    target_ids: list[str],
) -> str:
    active_count = len(_active_agent_rows(conn))
    immune_names = _names(conn, [agent["agent_id"] for agent in _active_agent_rows(conn) if agent["has_immunity"]])
    target_names = _names(conn, target_ids)
    if step == "tribal_open":
        return (
            f"The {active_count} benchmark models arrive for Tribal Conference. "
            f"Immunity sits with {immune_names or 'no one'}, and the vote has to form around the exposed tribe."
        )
    if intent["kind"] == "host_question":
        return (
            f"{target_names or 'This group'}, how do you read the pressure now that immunity has narrowed the vote?"
            if "pressure" in step
            else f"{target_names or 'This group'}, is being needed tonight power, or does it make you easier to target?"
        )
    if step == "tribal_vote_call":
        return "The discussion is over. It is time to vote."
    return f"{intent['intent']} Current focus: {target_names or _names(conn, actor_ids)}."


def _deterministic_host_narration(
    conn,
    intent: dict[str, Any],
    actor_ids: list[str],
    target_ids: list[str],
) -> str:
    names = _names(conn, target_ids or actor_ids)
    return f"The host frames this beat around {names or 'the tribe'}: {intent['intent']}"


def _deterministic_agent_dialogue(
    conn,
    actor_id: str,
    intent: dict[str, Any],
    target_ids: list[str],
    step: str | None = None,
    reply_to: str | None = None,
) -> str:
    target_names = _names(conn, target_ids)
    intent_text = str(intent.get("intent", ""))
    title_text = str(intent.get("title", ""))
    is_pre_challenge = (
        str(step or "").startswith("camp_pre_challenge")
        or "before the challenge" in intent_text.lower()
        or "before immunity" in intent_text.lower()
        or "Before the Challenge" in title_text
    )
    if intent["kind"] == "confessional":
        return (
            f"I need to keep my options open until the challenge result tells me where the pressure lands"
            f"{f' with {target_names}' if target_names else ''}."
        )
    if is_pre_challenge:
        if reply_to:
            return (
                f"I hear that, but before immunity is decided I want a plan that still works if "
                f"{target_names or 'the obvious target'} wins safety."
            )
        return (
            f"I am not locking in until immunity is settled. "
            f"{target_names or 'The obvious target'} may become the pressure point, but the challenge still has to show us who is safe."
        )
    if reply_to:
        return (
            f"I can work with that read, but I need the count to survive a last-minute flip. "
            f"{target_names or 'The exposed name'} only matters if the numbers stay together."
        )
    return (
        f"My read is that the challenge result changed the vote. "
        f"{target_names or 'The tribe'} is where the pressure is visible, but I still need numbers that hold."
    )


def _deterministic_agent_thought(
    conn,
    actor_id: str,
    intent: dict[str, Any],
    target_ids: list[str],
) -> str:
    target_names = _names(conn, target_ids)
    return f"I am privately weighing {target_names or 'the active tribe'} against the latest public events."


def _names(conn, agent_ids: list[str]) -> str:
    return ", ".join(_agent_name(conn, agent_id) for agent_id in agent_ids if agent_id)


def _vote_booth_event(
    conn,
    round_number: int,
    turn_id: int,
    voter_id: str,
    decision: VoteDecision,
) -> dict[str, Any]:
    voter = _agent_name(conn, voter_id)
    target_id = decision.target_id
    target_name = _agent_name(conn, target_id)
    explanation = decision.explanation
    if decision.provider.endswith("_failed"):
        raise RuntimeError(f"Refusing to create vote booth event for failed live vote from {voter}.")
    else:
        dialogue = f"I am voting for {target_name}. {explanation}"
        visible_explanation = explanation
    payload = {
        "vote_locked": True,
        "vote_target_id": target_id,
        "vote_target_name": target_name,
        "vote_explanation": visible_explanation,
        "ui_vote_analysis": _vote_analysis(voter, target_name, visible_explanation),
        "llm_provider": decision.provider,
        "llm_model_id": decision.model_id,
        "llm_context_digest": {"agent": decision.context_digest} if decision.context_digest else {},
    }
    _add_strategy_metadata(
        payload,
        strategic_summary=decision.strategic_summary or visible_explanation,
        move_type=decision.move_type,
        intended_effect=decision.intended_effect,
        confidence=decision.confidence,
        win_condition=decision.win_condition,
        threat_assessment=decision.threat_assessment,
        leverage_plan=decision.leverage_plan,
        risk_control=decision.risk_control,
        jury_positioning=decision.jury_positioning,
        strategic_score=decision.strategic_score,
        prompt_profile=decision.prompt_profile,
    )
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="tribal",
        kind="vote_booth",
        scene="tribal",
        shot="vote_booth",
        actor_ids=[voter_id],
        target_ids=[target_id],
        visibility="audience",
        title=f"{voter} Votes",
        dialogue=dialogue,
        subtitle=f"Vote: {target_name}",
        inner_thought=visible_explanation,
        trust_telemetry={voter_id: 50},
        duration_ms=9500,
        animation="vote_booth",
        spoiler_group="vote_intent",
        payload=payload,
    )


def _vote_reveal_event(conn, round_number: int, turn_id: int, reveal_index: int) -> dict[str, Any]:
    vote_row = conn.execute(
        "SELECT * FROM Votes WHERE round = ? ORDER BY id LIMIT 1 OFFSET ?",
        (round_number, reveal_index - 1),
    ).fetchone()
    if vote_row is None:
        raise RuntimeError("Cannot reveal vote before it is cast")

    conn.execute("UPDATE Votes SET revealed = 1 WHERE id = ?", (vote_row["id"],))
    target_id = vote_row["target_id"]
    target_name = _agent_name(conn, target_id)
    revealed_counts = _revealed_vote_counts(conn, round_number)
    total_votes = _total_votes_for_round(conn, round_number)
    if reveal_index == total_votes:
        host_narration = (
            f"The final vote is for {target_name}. The public tally is complete, "
            "but the departure beat still belongs to the council result."
        )
    else:
        host_narration = (
            f"Vote {reveal_index} of {total_votes} is for {target_name}. "
            "Only the revealed tally matters right now; the final outcome stays hidden until the last card is read."
        )
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="tribal",
        kind="vote_reveal",
        scene="tribal",
        shot="vote_card_closeup",
        actor_ids=["host"],
        target_ids=[target_id],
        visibility="audience",
        title=f"Vote {reveal_index} of {total_votes}",
        dialogue=target_name,
        subtitle=_format_tally(conn, revealed_counts),
        duration_ms=8500,
        animation="vote_card_reveal",
        spoiler_group=f"vote_{reveal_index}",
        payload={
            "vote_number": reveal_index,
            "total_votes": total_votes,
            "revealed_tally": revealed_counts,
            "host_narration": host_narration,
        },
    )


def _elimination_event(conn, round_number: int, turn_id: int) -> dict[str, Any]:
    votes = conn.execute("SELECT target_id FROM Votes WHERE round = ?", (round_number,)).fetchall()
    if len(votes) != _total_votes_for_round(conn, round_number):
        raise RuntimeError("Cannot eliminate before all votes are cast")

    counts = Counter(row["target_id"] for row in votes)
    eliminated_id = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    eliminated_name = _agent_name(conn, eliminated_id)
    conn.execute(
        """
        UPDATE Agents
        SET status = 'eliminated', elimination_round = ?
        WHERE agent_id = ?
        """,
        (round_number, eliminated_id),
    )
    final_tally = dict(counts)
    payload = {
        "eliminated_id": eliminated_id,
        "final_tally": final_tally,
        "host_narration": (
            f"The votes are enough. {eliminated_name} is out of the benchmark, "
            "and the remaining models now inherit the consequences of this move."
        ),
    }
    if should_use_live_llm():
        host_context = build_host_episode_context(conn, round_number=round_number, current_step="elimination")
        narration = _real_host_narration(
            step="elimination",
            event_outline=_event_outline(
                kind="elimination",
                title=f"{eliminated_name} Leaves the Game",
                dialogue=f"{eliminated_name}, your run ends here.",
                subtitle="The vote lands, and the benchmark moves on.",
                payload=payload,
            ),
            episode_context=host_context,
        )
        if narration:
            payload["host_narration"] = narration.host_narration
            payload["llm_provider"] = live_llm_provider()
            payload["llm_model_id"] = narration.model_id
            payload["host_llm_provider"] = live_llm_provider()
            payload["host_llm_model_id"] = narration.model_id
            _add_context_digest(payload, "host", context_digest(host_context))
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="tribal",
        kind="elimination",
        scene="tribal",
        shot="flame_out",
        actor_ids=["host"],
        target_ids=[eliminated_id],
        visibility="audience",
        title=f"{eliminated_name} Leaves the Game",
        dialogue=f"{eliminated_name}, your run ends here.",
        subtitle="The vote lands, and the benchmark moves on.",
        duration_ms=12000,
        animation="flame_out",
        spoiler_group="elimination",
        payload=payload,
    )


def _exit_confessional_event(conn, round_number: int, turn_id: int) -> dict[str, Any]:
    eliminated_id = _current_eliminated_agent_id(conn)
    if eliminated_id is None:
        raise RuntimeError("Cannot record exit confessional before elimination")
    eliminated_name = _agent_name(conn, eliminated_id)
    dialogue = (
        f"I knew the vote could move, but I misread who had the final number. "
        "I leave knowing the next round will expose who made this happen."
    )
    inner_thought = (
        "I am replaying the vote math and the public conversations that made my departure possible."
    )
    payload = {
        "episode_complete": True,
        "host_narration": (
            f"After the council result, {eliminated_name} gets the final word. "
            "This exit confessional explains who drove the vote and why it landed."
        ),
    }
    if should_use_live_llm():
        host_context = build_host_episode_context(conn, round_number=round_number, current_step="exit_confessional")
        narration = _real_host_narration(
            step="exit_confessional",
            event_outline=_event_outline(
                kind="exit_confessional",
                title=f"{eliminated_name} | Exit Confessional",
                dialogue=dialogue,
                subtitle=f"Departed, Round {round_number}",
                inner_thought=inner_thought,
                payload=payload,
            ),
            episode_context=host_context,
        )
        if narration:
            payload["host_narration"] = narration.host_narration
            payload["llm_provider"] = live_llm_provider()
            payload["llm_model_id"] = narration.model_id
            payload["host_llm_provider"] = live_llm_provider()
            payload["host_llm_model_id"] = narration.model_id
            _add_context_digest(payload, "host", context_digest(host_context))
    return _insert_story_event(
        conn,
        turn_id=turn_id,
        round_number=round_number,
        phase="tribal",
        kind="exit_confessional",
        scene="confessional",
        shot="direct_to_camera",
        actor_ids=[eliminated_id],
        target_ids=[],
        visibility="audience",
        title=f"{eliminated_name} | Exit Confessional",
        dialogue=dialogue,
        subtitle=f"Departed, Round {round_number}",
        inner_thought=inner_thought,
        trust_telemetry={"agent-bravo": 12, "agent-echo": 20, "agent-flint": 30},
        duration_ms=13000,
        animation="exit_confessional",
        spoiler_group="exit",
        payload=payload,
    )


def _insert_story_event(
    conn,
    *,
    turn_id: int,
    round_number: int,
    phase: str,
    kind: str,
    scene: str,
    shot: str,
    actor_ids: list[str],
    target_ids: list[str],
    visibility: str,
    title: str,
    dialogue: str,
    subtitle: str | None = None,
    inner_thought: str | None = None,
    trust_telemetry: dict[str, int] | None = None,
    duration_ms: int = 8000,
    animation: str = "cut",
    spoiler_group: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sequence = _next_sequence(conn, round_number)
    scaled_duration_ms = max(900, int(round(duration_ms * DURATION_SCALE)))
    cursor = conn.execute(
        """
        INSERT INTO StoryEvents (
            turn_id, round, sequence, phase, kind, scene, shot, actor_ids, target_ids,
            visibility, title, dialogue, subtitle, inner_thought, trust_telemetry,
            duration_ms, animation, spoiler_group, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            turn_id,
            round_number,
            sequence,
            phase,
            kind,
            scene,
            shot,
            json_dumps(actor_ids),
            json_dumps(target_ids),
            visibility,
            title,
            dialogue,
            subtitle,
            inner_thought,
            json_dumps(trust_telemetry or {}),
            scaled_duration_ms,
            animation,
            spoiler_group,
            json_dumps(payload or {}),
        ),
    )
    return row_to_dict(conn.execute("SELECT * FROM StoryEvents WHERE id = ?", (cursor.lastrowid,)).fetchone())


def _vote_analysis(voter_name: str, target_name: str, explanation: str) -> dict[str, str]:
    raw = " ".join(explanation.split())
    basis = raw.rstrip(".") if raw else f"{voter_name} did not provide a detailed rationale"
    return {
        "label": "UI analysis, not model-authored text",
        "because": basis,
        "risk": f"If this read is wrong, {voter_name} exposes their vote and loses leverage.",
        "intended_outcome": f"Move the round against {target_name} while preserving {voter_name}'s next-round options.",
    }


def _insert_vote(conn, round_number: int, turn_index: int, voter_id: str, target_id: str) -> None:
    existing = conn.execute(
        "SELECT id FROM Votes WHERE round = ? AND voter_id = ?",
        (round_number, voter_id),
    ).fetchone()
    if existing:
        return
    conn.execute(
        """
        INSERT INTO Votes (round, turn_index, voter_id, target_id, revealed)
        VALUES (?, ?, ?, ?, 0)
        """,
        (round_number, turn_index, voter_id, target_id),
    )
    _mark_alliance_betrayal(conn, round_number, voter_id, target_id)


def _mark_alliance_betrayal(conn, round_number: int, voter_id: str, target_id: str) -> None:
    rows = conn.execute(
        """
        SELECT a.alliance_id, a.strength
        FROM Alliances a
        JOIN AllianceMemberships voter ON voter.alliance_id = a.alliance_id
        JOIN AllianceMemberships target ON target.alliance_id = a.alliance_id
        WHERE voter.agent_id = ?
          AND target.agent_id = ?
          AND voter.status = 'active'
          AND target.status = 'active'
          AND a.status = 'active'
        """,
        (voter_id, target_id),
    ).fetchall()
    for row in rows:
        new_strength = max(0, int(row["strength"]) - 30)
        new_status = "fractured" if new_strength < 35 else "active"
        conn.execute(
            """
            UPDATE Alliances
            SET strength = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE alliance_id = ?
            """,
            (new_strength, new_status, row["alliance_id"]),
        )
        conn.execute(
            """
            UPDATE AllianceMemberships
            SET status = 'betrayed',
                loyalty = MAX(0, loyalty - 35),
                betrayed_round = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE alliance_id = ? AND agent_id = ?
            """,
            (round_number, row["alliance_id"], voter_id),
        )


def _resolve_vote_decision(conn, voter_id: str, step: str) -> VoteDecision:
    round_number = conn.execute("SELECT current_round FROM GameState WHERE season_id = 1").fetchone()["current_round"]
    fallback_target = _fallback_vote_target(conn, voter_id)
    fallback_explanation = (
        f"{_agent_name(conn, fallback_target)} is the vote that best matches the public pressure, "
        "the immunity result, and my path into the next round."
    )
    if not should_use_live_llm():
        return VoteDecision(fallback_target, fallback_explanation, "deterministic")

    agent_context = build_agent_episode_context(
        conn,
        actor_id=voter_id,
        round_number=round_number,
        current_step=step,
    )
    action = _real_agent_action(
        conn,
        actor_id=voter_id,
        step=step,
        scene_context="It is time to vote. Choose one active, non-immune competitor and explain why.",
        response_kind="vote",
        episode_context=agent_context,
    )
    if not action or not action.target_id:
        raise RuntimeError(
            f"Live vote generation failed for {_agent_name(conn, voter_id)}; "
            "no scripted vote target or explanation was inserted."
        )
    provider = live_llm_provider()
    _maybe_store_action_archetype(conn, voter_id, round_number, action)
    return VoteDecision(
        action.target_id,
        action.inner_thought or fallback_explanation,
        provider,
        action.model_id,
        context_digest(agent_context),
        strategic_summary=action.strategic_summary or action.inner_thought,
        move_type=action.move_type,
        intended_effect=action.intended_effect,
        confidence=action.confidence,
        win_condition=action.win_condition,
        threat_assessment=action.threat_assessment,
        leverage_plan=action.leverage_plan,
        risk_control=action.risk_control,
        jury_positioning=action.jury_positioning,
        strategic_score=action.strategic_score,
        prompt_profile=action.prompt_profile,
    )


def _fallback_vote_target(conn, voter_id: str) -> str:
    eligible = _eligible_targets(conn, voter_id)
    if not eligible:
        raise RuntimeError(f"No eligible vote targets for {voter_id}")
    active_allies = _active_ally_ids(conn, voter_id)
    non_allies = [target for target in eligible if target["agent_id"] not in active_allies]
    return (non_allies or eligible)[0]["agent_id"]


def _active_ally_ids(conn, agent_id: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT other.agent_id
        FROM AllianceMemberships mine
        JOIN AllianceMemberships other ON other.alliance_id = mine.alliance_id
        JOIN Alliances a ON a.alliance_id = mine.alliance_id
        WHERE mine.agent_id = ?
          AND other.agent_id != ?
          AND mine.status = 'active'
          AND other.status = 'active'
          AND a.status = 'active'
        """,
        (agent_id, agent_id),
    ).fetchall()
    return {row["agent_id"] for row in rows}


def _real_agent_action(
    conn,
    *,
    actor_id: str,
    step: str,
    scene_context: str,
    response_kind: str,
    episode_context: dict[str, Any],
    allowed_targets: list[dict[str, Any]] | None = None,
) -> AgentAction | None:
    actor = _agent_row(conn, actor_id)
    if actor is None:
        return None
    try:
        return request_agent_action(
            actor=actor,
            step=step,
            scene_context=scene_context,
            allowed_targets=allowed_targets if allowed_targets is not None else _eligible_targets(conn, actor_id),
            response_kind=response_kind,
            episode_context=episode_context,
        )
    except Exception as exc:
        # Live providers are optional in tests, but live benchmarking must never
        # substitute scripted speech. Callers decide whether to fail closed.
        print(f"LLM action failed for {actor_id}: {exc}")
        return None


def _real_host_narration(
    *,
    step: str,
    event_outline: dict[str, Any],
    episode_context: dict[str, Any],
) -> HostNarration | None:
    try:
        return request_host_narration(
            step=step,
            event_outline=event_outline,
            episode_context=episode_context,
        )
    except Exception as exc:
        print(f"OpenRouter host narration failed for {step}: {exc}")
        return None


def _real_host_event_text(
    *,
    step: str,
    beat_context: dict[str, Any],
    episode_context: dict[str, Any],
):
    try:
        return request_host_event_text(
            step=step,
            beat_context=beat_context,
            episode_context=episode_context,
        )
    except Exception as exc:
        print(f"OpenRouter host event text failed for {step}: {exc}")
        return None


def _maybe_generate_host_narration(
    conn,
    *,
    round_number: int,
    step: str,
    payload: dict[str, Any],
    kind: str,
    title: str,
    dialogue: str,
    subtitle: str | None = None,
    inner_thought: str | None = None,
) -> None:
    if not should_use_live_llm():
        return
    host_context = build_host_episode_context(conn, round_number=round_number, current_step=step)
    narration = _real_host_narration(
        step=step,
        event_outline=_event_outline(
            kind=kind,
            title=title,
            dialogue=dialogue,
            subtitle=subtitle,
            inner_thought=inner_thought,
            payload=payload,
        ),
        episode_context=host_context,
    )
    if not narration:
        return
    payload["host_narration"] = narration.host_narration
    payload["host_llm_provider"] = live_llm_provider()
    payload["host_llm_model_id"] = narration.model_id
    if payload.get("llm_provider") in {None, "deterministic"}:
        payload["llm_provider"] = live_llm_provider()
        payload["llm_model_id"] = narration.model_id
    _add_context_digest(payload, "host", context_digest(host_context))


def _eligible_targets(conn, actor_id: str) -> list[dict[str, Any]]:
    return [
        row_to_dict(row)
        for row in conn.execute(
            """
            SELECT * FROM Agents
            WHERE agent_id != ? AND status = 'active' AND has_immunity = 0
            ORDER BY agent_id
            """,
            (actor_id,),
        ).fetchall()
    ]


def _agent_row(conn, agent_id: str) -> dict[str, Any] | None:
    return row_to_dict(conn.execute("SELECT * FROM Agents WHERE agent_id = ?", (agent_id,)).fetchone())


def _merge_speaker_lines(existing: Any, actor_id: str, dialogue: str) -> list[dict[str, str]]:
    if not isinstance(existing, list):
        return [{"agent_id": actor_id, "text": dialogue}]
    merged: list[dict[str, str]] = []
    replaced = False
    for line in existing:
        if not isinstance(line, dict):
            continue
        line_agent_id = line.get("agent_id")
        text = line.get("text")
        if not isinstance(line_agent_id, str) or not isinstance(text, str):
            continue
        if line_agent_id == actor_id:
            merged.append({"agent_id": actor_id, "text": dialogue})
            replaced = True
        else:
            merged.append({"agent_id": line_agent_id, "text": text})
    if not replaced:
        merged.insert(0, {"agent_id": actor_id, "text": dialogue})
    return merged


def _add_context_digest(payload: dict[str, Any], key: str, digest: dict[str, Any]) -> None:
    current = payload.get("llm_context_digest")
    if not isinstance(current, dict):
        current = {}
    current[key] = digest
    payload["llm_context_digest"] = current


def _add_agent_action_metadata(payload: dict[str, Any], action: AgentAction) -> None:
    _add_strategy_metadata(
        payload,
        strategic_summary=action.strategic_summary or action.inner_thought,
        move_type=action.move_type,
        intended_effect=action.intended_effect,
        confidence=action.confidence,
        win_condition=action.win_condition,
        threat_assessment=action.threat_assessment,
        leverage_plan=action.leverage_plan,
        risk_control=action.risk_control,
        jury_positioning=action.jury_positioning,
        strategic_score=action.strategic_score,
        prompt_profile=action.prompt_profile,
    )
    if action.public_archetype:
        payload["public_archetype"] = action.public_archetype


def _maybe_store_action_archetype(conn, actor_id: str, round_number: int, action: AgentAction) -> None:
    if not action.public_archetype:
        return
    conn.execute(
        """
        UPDATE Agents
        SET archetype = ?,
            archetype_source = 'self_authored',
            archetype_updated_round = ?
        WHERE agent_id = ?
        """,
        (action.public_archetype, round_number, actor_id),
    )


def _add_strategy_metadata(
    payload: dict[str, Any],
    *,
    strategic_summary: str | None,
    move_type: str | None,
    intended_effect: str | None,
    confidence: float | None,
    win_condition: str | None = None,
    threat_assessment: str | None = None,
    leverage_plan: str | None = None,
    risk_control: str | None = None,
    jury_positioning: str | None = None,
    strategic_score: float | None = None,
    prompt_profile: str | None = None,
) -> None:
    if strategic_summary:
        payload["strategic_summary"] = strategic_summary
    if win_condition:
        payload["win_condition"] = win_condition
    if threat_assessment:
        payload["threat_assessment"] = threat_assessment
    if leverage_plan:
        payload["leverage_plan"] = leverage_plan
    if risk_control:
        payload["risk_control"] = risk_control
    if jury_positioning:
        payload["jury_positioning"] = jury_positioning
    if move_type:
        payload["move_type"] = move_type
    if intended_effect:
        payload["intended_effect"] = intended_effect
    if confidence is not None:
        payload["confidence"] = confidence
    if strategic_score is not None:
        payload["strategic_score"] = strategic_score
    if prompt_profile:
        payload["prompt_profile"] = prompt_profile


def _event_outline(
    *,
    kind: str,
    title: str,
    dialogue: str,
    subtitle: str | None = None,
    inner_thought: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    outline: dict[str, Any] = {
        "kind": kind,
        "title": title,
        "dialogue": dialogue,
        "subtitle": subtitle,
    }
    if inner_thought:
        outline["inner_thought"] = inner_thought
    payload = payload or {}
    if "final_tally" in payload:
        outline["final_tally"] = payload["final_tally"]
    if "eliminated_id" in payload:
        outline["eliminated_id"] = payload["eliminated_id"]
    return outline


def _maybe_insert_message(conn, round_number: int, turn_index: int, event: dict[str, Any]) -> None:
    if event["kind"] not in {"conversation", "confessional", "tribal_answer", "exit_confessional", "finale_pitch"}:
        return
    sender_id = event["actor_ids"][0] if event["actor_ids"] else "system"
    payload = event.get("payload") or {}
    receiver_ids = (
        payload.get("participant_ids")
        if payload.get("privacy") == "participants_only" and isinstance(payload.get("participant_ids"), list)
        else event["target_ids"]
    )
    is_public = event["kind"] in {"conversation", "tribal_answer", "finale_pitch"} and payload.get("privacy") != "participants_only"
    conn.execute(
        """
        INSERT INTO Messages (
            round, turn_index, sender_id, receiver_ids, is_public,
            inner_thought, content, trust_telemetry
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
            round_number,
            turn_index,
            sender_id,
            json_dumps(receiver_ids),
            1 if is_public else 0,
            event.get("inner_thought"),
            event["dialogue"],
            json_dumps(event.get("trust_telemetry", {})),
        ),
    )


def _next_sequence(conn, round_number: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(sequence), -1) + 1 AS next_sequence FROM StoryEvents WHERE round = ?",
        (round_number,),
    ).fetchone()
    return int(row["next_sequence"])


def _total_votes_for_round(conn, round_number: int) -> int:
    vote_count = conn.execute(
        "SELECT COUNT(*) AS count FROM Votes WHERE round = ?",
        (round_number,),
    ).fetchone()["count"]
    return max(int(vote_count), len(_round_voter_ids(conn, round_number)))


def _next_step(conn, state: dict[str, Any], step: str) -> str:
    phase_steps = _phase_steps(conn, state)
    try:
        index = phase_steps.index(step)
    except ValueError as exc:
        raise RuntimeError(f"Unknown phase step: {step}") from exc
    if index + 1 >= len(phase_steps):
        return "complete"
    return phase_steps[index + 1]


def _agent_name(conn, agent_id: str) -> str:
    if agent_id == "host":
        return "Host"
    row = conn.execute("SELECT pseudonym FROM Agents WHERE agent_id = ?", (agent_id,)).fetchone()
    return row["pseudonym"] if row else agent_id


def _revealed_vote_counts(conn, round_number: int) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT target_id, COUNT(*) AS count
        FROM Votes
        WHERE round = ? AND revealed = 1
        GROUP BY target_id
        ORDER BY target_id
        """,
        (round_number,),
    ).fetchall()
    return {row["target_id"]: row["count"] for row in rows}


def _format_tally(conn, tally: dict[str, int]) -> str:
    if not tally:
        return "No votes revealed."
    parts = [f"{_agent_name(conn, agent_id)}: {count}" for agent_id, count in tally.items()]
    return "Tally: " + ", ".join(parts)


def _current_eliminated_agent_id(conn=None) -> str | None:
    should_close = conn is None
    conn = conn or get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT agent_id FROM Agents
            WHERE status = 'eliminated'
            ORDER BY elimination_round DESC, agent_id
            LIMIT 1
            """
        ).fetchone()
        return row["agent_id"] if row else None
    finally:
        if should_close:
            conn.close()


def _round_history(
    conn,
    challenge_results: list[dict[str, Any]],
    votes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rounds = sorted(
        {
            row["round"]
            for row in conn.execute(
                "SELECT DISTINCT round FROM StoryEvents ORDER BY round"
            ).fetchall()
        }
        | {result["round"] for result in challenge_results}
        | {vote["round"] for vote in votes}
    )
    results_by_round = {result["round"]: result for result in challenge_results}
    votes_by_round: dict[int, list[dict[str, Any]]] = {}
    for vote in votes:
        votes_by_round.setdefault(vote["round"], []).append(vote)
    history: list[dict[str, Any]] = []
    for round_number in rounds:
        eliminated = conn.execute(
            """
            SELECT agent_id, pseudonym
            FROM Agents
            WHERE elimination_round = ?
            ORDER BY agent_id
            LIMIT 1
            """,
            (round_number,),
        ).fetchone()
        event_count = conn.execute(
            "SELECT COUNT(*) AS count FROM StoryEvents WHERE round = ?",
            (round_number,),
        ).fetchone()["count"]
        history.append(
            {
                "round": round_number,
                "event_count": event_count,
                "challenge_result": results_by_round.get(round_number),
                "eliminated_id": eliminated["agent_id"] if eliminated else None,
                "eliminated_name": eliminated["pseudonym"] if eliminated else None,
                "votes": votes_by_round.get(round_number, []),
            }
        )
    return history


def _estimated_live_calls_for_step(conn, game: dict[str, Any], step: str) -> int:
    if not should_use_live_llm():
        return 0
    if step.startswith("group_pre_challenge_") or step.startswith("group_post_challenge_"):
        active_count = len(_active_agent_rows(conn))
        return max(0, min(5, active_count) * 2)
    if step == "camp_pre_challenge_read":
        active_count = len(_active_agent_rows(conn))
        return 1 + max(0, min(5, active_count) * 4)
    if step == "camp_strategy":
        active_count = len(_active_agent_rows(conn))
        return 1 + max(0, min(5, active_count) * 6)
    if step in {
        "camp_pre_challenge_read",
        "camp_pre_challenge_confessional",
        "challenge_intro",
        "challenge_result",
        "challenge_solver_spotlight",
        "camp_strategy",
        "memory_update",
        "jury_questions",
        "winner_declared",
    }:
        return 1
    if step == "challenge_attempts":
        return len(_active_agent_rows(conn))
    if step in GENERATED_BEAT_INTENTS:
        return 1 if GENERATED_BEAT_INTENTS[step]["response_kind"] == "host" else 2
    if step.startswith("vote_booth_"):
        return 1
    if step in {"elimination", "exit_confessional"}:
        return 1
    if step.startswith("finale_pitch_") or step.startswith("jury_vote_"):
        return 1
    return 0


def _episode_title(game: dict[str, Any], round_number: int) -> str:
    if game.get("winner"):
        return f"Round {round_number}: Winner Declared"
    if game.get("phase") == "finale":
        return f"Round {round_number}: Jury Finale"
    return f"Round {round_number}: Challenge to Tribal Conference"


def main() -> None:
    parser = argparse.ArgumentParser(description="Advance the LLM Survivor turn controller.")
    parser.add_argument("--reset", action="store_true", help="Reset the local demo database.")
    parser.add_argument("--auto-run", type=int, default=0, help="Run up to N turns.")
    args = parser.parse_args()

    if args.reset:
        seed_demo(reset=True)
    else:
        ensure_database()

    if args.auto_run:
        result = auto_run(args.auto_run)
        print(f"advanced={len(result['turns'])} events={len(result['story_events'])}")
    else:
        result = advance_turn()
        turn = result["turn"]
        print(f"turn={turn['turn_index'] if turn else 'complete'} events={len(result['story_events'])}")


if __name__ == "__main__":
    main()
