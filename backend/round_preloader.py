from __future__ import annotations

from typing import Any

from .database import ensure_database, get_db_connection, json_dumps, row_to_dict
from .llm_config import failed_llm_provider, live_llm_provider, should_use_live_llm
from .llm_context import build_agent_episode_context, build_host_episode_context, context_digest
from .openrouter_client import request_agent_action, request_host_narration


PRELOAD_PHASE = "round"


def get_next_round_preload_status() -> dict[str, Any] | None:
    ensure_database()
    conn = get_db_connection()
    try:
        state = row_to_dict(conn.execute("SELECT * FROM GameState WHERE season_id = 1").fetchone())
        if state is None:
            return None
        return _latest_status(conn, state["season_id"], state["current_round"])
    finally:
        conn.close()


def start_next_round_preload(run_inline: bool = False) -> dict[str, Any]:
    ensure_database()
    conn = get_db_connection()
    try:
        state = row_to_dict(conn.execute("SELECT * FROM GameState WHERE season_id = 1").fetchone())
        if state is None:
            raise RuntimeError("GameState is not seeded")
        source_round = state["current_round"]
        target_round = source_round + 1
        existing = _latest_status(conn, state["season_id"], source_round)
        if existing and existing["status"] in {"pending", "running", "complete"}:
            return existing

        provider = live_llm_provider() if should_use_live_llm() else "deterministic"
        if existing:
            conn.execute(
                """
                UPDATE NextRoundPreloads
                SET status = 'pending',
                    provider = ?,
                    event_count = 0,
                    context_digest = '{}',
                    generated_payload = '{}',
                    error_message = NULL,
                    started_at = CURRENT_TIMESTAMP,
                    completed_at = NULL
                WHERE id = ?
                """,
                (provider, existing["id"]),
            )
            preload_id = existing["id"]
        else:
            cursor = conn.execute(
                """
                INSERT INTO NextRoundPreloads (
                    season_id, source_round, target_round, phase, status, provider
                ) VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (state["season_id"], source_round, target_round, PRELOAD_PHASE, provider),
            )
            preload_id = int(cursor.lastrowid)
        conn.commit()
    finally:
        conn.close()

    if run_inline:
        run_next_round_preload(preload_id)
    return get_preload_status(preload_id) or {"id": preload_id, "status": "pending"}


def run_next_round_preload(preload_id: int) -> None:
    conn = get_db_connection()
    try:
        preload = row_to_dict(conn.execute("SELECT * FROM NextRoundPreloads WHERE id = ?", (preload_id,)).fetchone())
        if preload is None or preload["status"] == "complete":
            return
        conn.execute(
            """
            UPDATE NextRoundPreloads
            SET status = 'running', started_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (preload_id,),
        )
        conn.commit()

        source_round = preload["source_round"]
        target_round = preload["target_round"]
        provider = live_llm_provider() if should_use_live_llm() else "deterministic"
        context_conn = get_db_connection()
        try:
            agent_responses = _build_agent_responses(context_conn, source_round, target_round, provider)
            host_response = _build_host_response(context_conn, source_round, target_round, provider)
            host_context = build_host_episode_context(
                context_conn,
                round_number=source_round,
                current_step=f"preload_round_{target_round}",
            )
        finally:
            context_conn.close()

        generated_payload = {
            "target_round": target_round,
            "phase": PRELOAD_PHASE,
            "provider": provider,
            "agent_responses": agent_responses,
            "host_response": host_response,
        }
        digest = {
            "visibility": "preload_status_only",
            "provider": provider,
            "source_round": source_round,
            "target_round": target_round,
            "agent_response_count": len(agent_responses),
            "host_context": context_digest(host_context),
        }
        conn.execute(
            """
            UPDATE NextRoundPreloads
            SET status = 'complete',
                provider = ?,
                event_count = ?,
                context_digest = ?,
                generated_payload = ?,
                error_message = NULL,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                provider,
                len(agent_responses) + (1 if host_response else 0),
                json_dumps(digest),
                json_dumps(generated_payload),
                preload_id,
            ),
        )
        conn.commit()
    except Exception as exc:
        conn.execute(
            """
            UPDATE NextRoundPreloads
            SET status = 'failed', error_message = ?, completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (str(exc), preload_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_preload_status(preload_id: int) -> dict[str, Any] | None:
    conn = get_db_connection()
    try:
        row = row_to_dict(conn.execute("SELECT * FROM NextRoundPreloads WHERE id = ?", (preload_id,)).fetchone())
        return _public_status(row)
    finally:
        conn.close()


def _latest_status(conn, season_id: int, source_round: int) -> dict[str, Any] | None:
    row = row_to_dict(
        conn.execute(
            """
            SELECT * FROM NextRoundPreloads
            WHERE season_id = ? AND source_round = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (season_id, source_round),
        ).fetchone()
    )
    return _public_status(row)


def _public_status(row: dict[str, Any] | None) -> dict[str, Any] | None:
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


def _build_agent_responses(conn, source_round: int, target_round: int, provider: str) -> list[dict[str, Any]]:
    agents = [
        row_to_dict(row)
        for row in conn.execute(
            "SELECT * FROM Agents WHERE status = 'active' ORDER BY agent_id"
        ).fetchall()
    ]
    responses: list[dict[str, Any]] = []
    for agent in agents:
        actor_id = agent["agent_id"]
        episode_context = build_agent_episode_context(
            conn,
            actor_id=actor_id,
            round_number=source_round,
            current_step=f"preload_round_{target_round}_strategy",
        )
        allowed_targets = [candidate for candidate in agents if candidate["agent_id"] != actor_id]
        action = None
        response_provider = provider
        if provider == live_llm_provider():
            try:
                action = request_agent_action(
                    actor=agent,
                    step=f"preload_round_{target_round}_strategy",
                    scene_context=(
                        f"source_round={source_round}; target_round={target_round}; "
                        "purpose=next_round_preload"
                    ),
                    allowed_targets=allowed_targets,
                    response_kind="strategy",
                    episode_context=episode_context,
                )
            except Exception as exc:
                response_provider = failed_llm_provider()
                action = None
                error = str(exc)
            else:
                error = None
        else:
            error = None

        if action is None:
            dialogue = (
                f"{agent['pseudonym']} starts round {target_round} by reassessing who gained power "
                f"from the last vote."
            )
            inner_thought = (
                "The next move should preserve options before the new target becomes obvious."
            )
            model_id = agent.get("model_id")
            target_id = None
        else:
            dialogue = action.dialogue
            inner_thought = action.inner_thought
            model_id = action.model_id
            target_id = action.target_id

        response = {
            "agent_id": actor_id,
            "dialogue": dialogue,
            "inner_thought": inner_thought,
            "target_id": target_id,
            "llm_provider": response_provider,
            "llm_model_id": model_id,
            "llm_context_digest": context_digest(episode_context),
        }
        if error:
            response["error"] = error
        responses.append(response)
    return responses


def _build_host_response(conn, source_round: int, target_round: int, provider: str) -> dict[str, Any]:
    episode_context = build_host_episode_context(
        conn,
        round_number=source_round,
        current_step=f"preload_round_{target_round}_host",
    )
    if provider == live_llm_provider():
        try:
            narration = request_host_narration(
                step=f"preload_round_{target_round}_host",
                event_outline={
                    "kind": "next_round_setup",
                    "title": f"Round {target_round} Setup",
                    "dialogue": f"The island game moves from round {source_round} into round {target_round}.",
                    "subtitle": "Prepared while the prior round replays.",
                },
                episode_context=episode_context,
            )
            return {
                "host_narration": narration.host_narration,
                "llm_provider": live_llm_provider(),
                "llm_model_id": narration.model_id,
                "llm_context_digest": context_digest(episode_context),
            }
        except Exception as exc:
            return {
                "host_narration": f"Round {target_round} is already taking shape while the last vote plays out.",
                "llm_provider": failed_llm_provider(),
                "llm_model_id": None,
                "llm_context_digest": context_digest(episode_context),
                "error": str(exc),
            }
    return {
        "host_narration": f"Round {target_round} is already taking shape while the last vote plays out.",
        "llm_provider": "deterministic",
        "llm_model_id": None,
        "llm_context_digest": context_digest(episode_context),
    }
