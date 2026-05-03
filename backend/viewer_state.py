from __future__ import annotations

from typing import Any

from .database import ensure_database, get_db_connection, row_to_dict


def get_viewer_state() -> dict[str, Any]:
    ensure_database()
    conn = get_db_connection()
    try:
        state = _ensure_viewer_state(conn)
        conn.commit()
        return _public_viewer_state(state)
    finally:
        conn.close()


def update_viewer_state(
    replay_index: int | None = None,
    is_playing: bool | None = None,
    round_number: int | None = None,
    phase: str | None = None,
) -> dict[str, Any]:
    ensure_database()
    conn = get_db_connection()
    try:
        state = _ensure_viewer_state(conn)
        target_round = round_number if round_number is not None else state["round"]
        target_phase = phase if phase is not None else state["phase"]
        target_index = state["replay_index"] if replay_index is None else max(0, replay_index)
        target_index = _clamp_replay_index(conn, target_round, target_phase, target_index)
        playing_value = state["is_playing"] if is_playing is None else int(is_playing)

        conn.execute(
            """
            UPDATE ViewerState
            SET round = ?,
                phase = ?,
                replay_index = ?,
                is_playing = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE season_id = 1
            """,
            (target_round, target_phase, target_index, playing_value),
        )
        conn.commit()
        updated = row_to_dict(conn.execute("SELECT * FROM ViewerState WHERE season_id = 1").fetchone())
        return _public_viewer_state(updated)
    finally:
        conn.close()


def viewer_state_summary(conn, game: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if game is None:
        return None
    state = _ensure_viewer_state(conn)
    conn.commit()
    return _public_viewer_state(state)


def _ensure_viewer_state(conn) -> dict[str, Any]:
    row = row_to_dict(conn.execute("SELECT * FROM ViewerState WHERE season_id = 1").fetchone())
    if row is not None:
        return row
    game = row_to_dict(conn.execute("SELECT * FROM GameState WHERE season_id = 1").fetchone())
    if game is None:
        raise RuntimeError("GameState is not seeded")
    conn.execute(
        """
        INSERT INTO ViewerState (
            season_id, round, phase, replay_index, is_playing, updated_at
        ) VALUES (?, ?, ?, 0, 0, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        """,
        (game["season_id"], game["current_round"], game["phase"]),
    )
    return row_to_dict(conn.execute("SELECT * FROM ViewerState WHERE season_id = 1").fetchone())


def _clamp_replay_index(conn, round_number: int, phase: str, replay_index: int) -> int:
    if phase == "round":
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM StoryEvents
            WHERE round = ?
            """,
            (round_number,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM StoryEvents
            WHERE round = ? AND phase = ?
            """,
            (round_number, phase),
        ).fetchone()
    event_count = row["count"] if row else 0
    if event_count <= 0:
        return 0
    return min(replay_index, event_count - 1)


def _public_viewer_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if state is None:
        raise RuntimeError("ViewerState is not seeded")
    return {
        "season_id": state["season_id"],
        "round": state["round"],
        "phase": state["phase"],
        "replay_index": state["replay_index"],
        "is_playing": bool(state["is_playing"]),
        "updated_at": state["updated_at"],
    }
