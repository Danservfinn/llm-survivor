from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .challenge_fixtures import CHALLENGE_PUZZLES
from .fixtures import DEMO_AGENTS
from .model_rosters import agents_for_roster

DATABASE_PATH = Path(os.environ.get("SURVIVOR_DB_PATH", Path(__file__).with_name("survivor.db")))

JSON_COLUMNS = {
    "receiver_ids",
    "trust_telemetry",
    "state_delta",
    "actor_ids",
    "target_ids",
    "payload",
    "context_digest",
    "generated_payload",
    "alignment_json",
    "examples",
    "answer",
    "attempt_payload",
    "result_payload",
    "immunity_agent_ids",
    "transcript",
}


def json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def json_loads(value: str | None, fallback: Any = None) -> Any:
    if value is None or value == "":
        return fallback
    return json.loads(value)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key in JSON_COLUMNS.intersection(data):
        data[key] = json_loads(data[key], [] if key.endswith("_ids") else {})
    return data


def get_db_connection(path: Path | str | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path else DATABASE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_database(reset: bool = False, path: Path | str | None = None) -> None:
    db_path = Path(path) if path else DATABASE_PATH
    if reset and db_path.exists():
        db_path.unlink()

    conn = get_db_connection(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS GameState (
                season_id INTEGER PRIMARY KEY,
                current_round INTEGER NOT NULL,
                phase TEXT NOT NULL,
                phase_step TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                is_merged INTEGER NOT NULL DEFAULT 1,
                winner TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS Agents (
                agent_id TEXT PRIMARY KEY,
                pseudonym TEXT NOT NULL UNIQUE,
                model_id TEXT NOT NULL DEFAULT '',
                archetype TEXT NOT NULL,
                team_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                has_immunity INTEGER NOT NULL DEFAULT 0,
                confessional_memory TEXT NOT NULL DEFAULT '',
                action_points INTEGER NOT NULL DEFAULT 0,
                elimination_round INTEGER,
                portrait_seed TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS GroupDiscussions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round INTEGER NOT NULL,
                turn_id INTEGER,
                stage TEXT NOT NULL,
                proposer_id TEXT NOT NULL,
                target_size INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'proposed',
                topic TEXT NOT NULL DEFAULT '',
                privacy TEXT NOT NULL DEFAULT 'participants_only',
                alliance_id TEXT,
                transcript TEXT NOT NULL DEFAULT '[]',
                summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS GroupDiscussionParticipants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discussion_id INTEGER NOT NULL,
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'invitee',
                response_status TEXT NOT NULL DEFAULT 'pending',
                join_intent TEXT NOT NULL DEFAULT 'none',
                line_order INTEGER,
                line_text TEXT NOT NULL DEFAULT '',
                rationale TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT 'deterministic',
                model_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(discussion_id, agent_id),
                FOREIGN KEY(discussion_id) REFERENCES GroupDiscussions(id)
            );

            CREATE TABLE IF NOT EXISTS Alliances (
                alliance_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                round_created INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                strength INTEGER NOT NULL DEFAULT 60,
                summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS AllianceMemberships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alliance_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                loyalty INTEGER NOT NULL DEFAULT 60,
                joined_round INTEGER NOT NULL,
                last_reinforced_round INTEGER,
                betrayed_round INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(alliance_id, agent_id),
                FOREIGN KEY(alliance_id) REFERENCES Alliances(alliance_id)
            );

            CREATE TABLE IF NOT EXISTS Messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round INTEGER NOT NULL,
                turn_index INTEGER NOT NULL,
                sender_id TEXT NOT NULL,
                receiver_ids TEXT NOT NULL,
                is_public INTEGER NOT NULL DEFAULT 0,
                inner_thought TEXT,
                content TEXT NOT NULL,
                trust_telemetry TEXT NOT NULL DEFAULT '{}',
                timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS Votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round INTEGER NOT NULL,
                turn_index INTEGER NOT NULL,
                voter_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                revealed INTEGER NOT NULL DEFAULT 0,
                is_revote INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS Turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER NOT NULL,
                round INTEGER NOT NULL,
                turn_index INTEGER NOT NULL,
                phase TEXT NOT NULL,
                phase_step TEXT NOT NULL,
                actor_id TEXT,
                input_summary TEXT NOT NULL,
                output_summary TEXT NOT NULL DEFAULT '',
                state_delta TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'committed',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS StoryEvents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turn_id INTEGER NOT NULL,
                round INTEGER NOT NULL,
                sequence INTEGER NOT NULL,
                phase TEXT NOT NULL,
                kind TEXT NOT NULL,
                scene TEXT NOT NULL,
                shot TEXT NOT NULL,
                actor_ids TEXT NOT NULL DEFAULT '[]',
                target_ids TEXT NOT NULL DEFAULT '[]',
                visibility TEXT NOT NULL DEFAULT 'audience',
                title TEXT NOT NULL,
                dialogue TEXT NOT NULL DEFAULT '',
                subtitle TEXT,
                inner_thought TEXT,
                trust_telemetry TEXT NOT NULL DEFAULT '{}',
                duration_ms INTEGER NOT NULL DEFAULT 8000,
                animation TEXT NOT NULL DEFAULT 'cut',
                spoiler_group TEXT,
                payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(turn_id) REFERENCES Turns(id)
            );

            CREATE TABLE IF NOT EXISTS VoiceLines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_event_id INTEGER NOT NULL,
                round INTEGER NOT NULL,
                event_sequence INTEGER NOT NULL,
                line_index INTEGER NOT NULL,
                speaker_id TEXT NOT NULL,
                speaker_label TEXT NOT NULL,
                voice_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                text TEXT NOT NULL,
                text_hash TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                audio_path TEXT,
                audio_url TEXT,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                start_ms INTEGER NOT NULL DEFAULT 0,
                end_ms INTEGER NOT NULL DEFAULT 0,
                alignment_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(story_event_id) REFERENCES StoryEvents(id)
            );

            CREATE TABLE IF NOT EXISTS NextRoundPreloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER NOT NULL,
                source_round INTEGER NOT NULL,
                target_round INTEGER NOT NULL,
                phase TEXT NOT NULL DEFAULT 'tribal',
                status TEXT NOT NULL DEFAULT 'pending',
                provider TEXT NOT NULL DEFAULT 'deterministic',
                event_count INTEGER NOT NULL DEFAULT 0,
                context_digest TEXT NOT NULL DEFAULT '{}',
                generated_payload TEXT NOT NULL DEFAULT '{}',
                error_message TEXT,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS ChallengePuzzles (
                puzzle_id TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                examples TEXT NOT NULL DEFAULT '[]',
                answer TEXT NOT NULL DEFAULT '{}',
                difficulty TEXT NOT NULL DEFAULT 'easy',
                eligibility TEXT NOT NULL DEFAULT 'both',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ChallengeAttempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round INTEGER NOT NULL,
                puzzle_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                tribe_id TEXT,
                provider TEXT NOT NULL DEFAULT 'deterministic',
                model_id TEXT,
                answer TEXT NOT NULL DEFAULT '',
                is_correct INTEGER NOT NULL DEFAULT 0,
                response_ms INTEGER NOT NULL DEFAULT 0,
                attempt_order INTEGER NOT NULL DEFAULT 0,
                attempt_payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(puzzle_id) REFERENCES ChallengePuzzles(puzzle_id)
            );

            CREATE TABLE IF NOT EXISTS ChallengeResults (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round INTEGER NOT NULL UNIQUE,
                puzzle_id TEXT NOT NULL,
                challenge_type TEXT NOT NULL DEFAULT 'individual',
                winning_agent_id TEXT,
                winning_tribe_id TEXT,
                immunity_agent_ids TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'deterministic',
                result_payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(puzzle_id) REFERENCES ChallengePuzzles(puzzle_id)
            );

            CREATE TABLE IF NOT EXISTS JuryVotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round INTEGER NOT NULL,
                juror_id TEXT NOT NULL,
                finalist_id TEXT NOT NULL,
                rationale TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT 'deterministic',
                model_id TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ViewerState (
                season_id INTEGER PRIMARY KEY,
                round INTEGER NOT NULL,
                phase TEXT NOT NULL DEFAULT 'tribal',
                replay_index INTEGER NOT NULL DEFAULT 0,
                is_playing INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_story_events_round_sequence
                ON StoryEvents(round, sequence);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_voice_lines_event_line
                ON VoiceLines(story_event_id, line_index);
            CREATE INDEX IF NOT EXISTS idx_voice_lines_cache_key
                ON VoiceLines(cache_key);
            CREATE INDEX IF NOT EXISTS idx_voice_lines_round_sequence
                ON VoiceLines(round, event_sequence);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_next_round_preloads_round
                ON NextRoundPreloads(season_id, source_round, target_round, phase);
            CREATE INDEX IF NOT EXISTS idx_next_round_preloads_status
                ON NextRoundPreloads(status);
            CREATE INDEX IF NOT EXISTS idx_challenge_attempts_round
                ON ChallengeAttempts(round, attempt_order);
            CREATE INDEX IF NOT EXISTS idx_jury_votes_round
                ON JuryVotes(round);
            CREATE INDEX IF NOT EXISTS idx_turns_round_turn_index
                ON Turns(round, turn_index);
            CREATE INDEX IF NOT EXISTS idx_votes_round_revealed
                ON Votes(round, revealed);
            CREATE INDEX IF NOT EXISTS idx_group_discussions_round
                ON GroupDiscussions(round, stage);
            CREATE INDEX IF NOT EXISTS idx_group_participants_agent
                ON GroupDiscussionParticipants(agent_id, response_status);
            CREATE INDEX IF NOT EXISTS idx_alliance_members_agent
                ON AllianceMemberships(agent_id, status);
            """
        )
        _seed_challenge_puzzles(conn)
        _ensure_column(conn, "Agents", "model_id", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "Agents", "archetype_source", "TEXT NOT NULL DEFAULT 'seeded'")
        _ensure_column(conn, "Agents", "archetype_updated_round", "INTEGER")
        _ensure_agent_model_ids(conn)
        _ensure_viewer_state(conn)
        conn.commit()
    finally:
        conn.close()


def seed_demo(
    reset: bool = False,
    path: Path | str | None = None,
    roster_preset: str | None = None,
) -> None:
    init_database(reset=reset, path=path)
    conn = get_db_connection(path)
    try:
        row = conn.execute("SELECT COUNT(*) AS count FROM GameState").fetchone()
        if row and row["count"] > 0 and not reset:
            return

        conn.execute("DELETE FROM VoiceLines")
        conn.execute("DELETE FROM NextRoundPreloads")
        conn.execute("DELETE FROM ViewerState")
        conn.execute("DELETE FROM AllianceMemberships")
        conn.execute("DELETE FROM Alliances")
        conn.execute("DELETE FROM GroupDiscussionParticipants")
        conn.execute("DELETE FROM GroupDiscussions")
        conn.execute("DELETE FROM StoryEvents")
        conn.execute("DELETE FROM Turns")
        conn.execute("DELETE FROM JuryVotes")
        conn.execute("DELETE FROM ChallengeResults")
        conn.execute("DELETE FROM ChallengeAttempts")
        conn.execute("DELETE FROM Votes")
        conn.execute("DELETE FROM Messages")
        conn.execute("DELETE FROM Agents")
        conn.execute("DELETE FROM GameState")
        _seed_challenge_puzzles(conn)

        conn.execute(
            """
            INSERT INTO GameState (
                season_id, current_round, phase, phase_step, turn_index, is_merged
            ) VALUES (1, 7, 'round', 'camp_pre_challenge_read', 0, 1)
            """
        )
        conn.execute(
            """
            INSERT INTO ViewerState (
                season_id, round, phase, replay_index, is_playing
            ) VALUES (1, 7, 'round', 0, 0)
            """
        )

        conn.executemany(
            """
            INSERT INTO Agents (
                agent_id, pseudonym, model_id, archetype, team_id, status, has_immunity,
                confessional_memory, action_points, elimination_round, portrait_seed,
                archetype_source, archetype_updated_round
            ) VALUES (
                :agent_id, :pseudonym, :model_id, :archetype, :team_id, 'active', :has_immunity,
                :confessional_memory, 0, NULL, :portrait_seed, 'seeded', NULL
            )
            """,
            agents_for_roster(roster_preset),
        )
        conn.commit()
    finally:
        conn.close()


def ensure_database() -> None:
    if _database_ready():
        return
    init_database(reset=False)
    seed_demo(reset=False)


def _database_ready() -> bool:
    if not DATABASE_PATH.exists():
        return False
    conn = get_db_connection()
    try:
        required_tables = {
            "GameState",
            "Agents",
            "Turns",
            "StoryEvents",
            "ViewerState",
            "GroupDiscussions",
            "GroupDiscussionParticipants",
            "Alliances",
            "AllianceMemberships",
            "ChallengePuzzles",
            "ChallengeAttempts",
            "ChallengeResults",
            "JuryVotes",
        }
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if not required_tables.issubset(tables):
            return False
        game = conn.execute("SELECT 1 FROM GameState WHERE season_id = 1").fetchone()
        return game is not None
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_agent_model_ids(conn: sqlite3.Connection) -> None:
    missing_ids = {
        row["agent_id"]
        for row in conn.execute(
            "SELECT agent_id FROM Agents WHERE COALESCE(model_id, '') = ''"
        ).fetchall()
    }
    if not missing_ids:
        return
    conn.executemany(
        "UPDATE Agents SET model_id = ? WHERE agent_id = ? AND COALESCE(model_id, '') = ''",
        [
            (agent["model_id"], agent["agent_id"])
            for agent in DEMO_AGENTS
            if agent["agent_id"] in missing_ids
        ],
    )


def _seed_challenge_puzzles(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT OR REPLACE INTO ChallengePuzzles (
            puzzle_id, prompt, examples, answer, difficulty, eligibility
        ) VALUES (
            :puzzle_id, :prompt, :examples, :answer, :difficulty, :eligibility
        )
        """,
        [
            {
                **puzzle,
                "examples": json_dumps(puzzle["examples"]),
                "answer": json_dumps(puzzle["answer"]),
            }
            for puzzle in CHALLENGE_PUZZLES
        ],
    )


def _ensure_viewer_state(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) AS count FROM ViewerState").fetchone()
    if row and row["count"] > 0:
        return
    game = conn.execute("SELECT season_id, current_round, phase FROM GameState WHERE season_id = 1").fetchone()
    if game is None:
        return
    conn.execute(
        """
        INSERT INTO ViewerState (
            season_id, round, phase, replay_index, is_playing
        ) VALUES (?, ?, ?, 0, 0)
        """,
        (game["season_id"], game["current_round"], game["phase"]),
    )
