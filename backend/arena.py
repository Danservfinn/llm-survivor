from __future__ import annotations

import hashlib
import json
from typing import Any

from .database import ensure_database, get_db_connection, json_dumps, row_to_dict

ROOM_ID = "room-demo"
ENTRY_AMOUNT_CENTS = 2500
HOUSE_FEE_RATE = 0.10
MAX_SEATS = 16
BASE_USDC_NETWORK = "eip155:8453"
BASE_USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

CPU_PROFILES = [
    ("cpu-orchid", "Orchid", "openai/gpt-4.1-mini", "patient alliance gardener"),
    ("cpu-cinder", "Cinder", "anthropic/claude-3.5-haiku", "blunt challenge grinder"),
    ("cpu-rune", "Rune", "google/gemini-2.5-flash", "pattern-reading swing vote"),
    ("cpu-vale", "Vale", "meta-llama/llama-3.3-70b-instruct", "quiet bloc builder"),
    ("cpu-marrow", "Marrow", "mistralai/mistral-large", "loyalist with sharp memory"),
    ("cpu-glass", "Glass", "deepseek/deepseek-chat", "risk-taking strategist"),
    ("cpu-sol", "Sol", "x-ai/grok-4.3", "chaotic narrator hunter"),
    ("cpu-pike", "Pike", "qwen/qwen3-32b", "vote math tactician"),
    ("cpu-lumen", "Lumen", "openai/gpt-4.1-mini", "empathetic information broker"),
    ("cpu-bramble", "Bramble", "anthropic/claude-3.5-haiku", "defensive social shield"),
    ("cpu-nyx", "Nyx", "google/gemini-2.5-flash", "late-game jury manager"),
    ("cpu-cobalt", "Cobalt", "meta-llama/llama-3.3-70b-instruct", "visible power player"),
    ("cpu-sable", "Sable", "mistralai/mistral-large", "low-profile opportunist"),
    ("cpu-ember", "Ember", "deepseek/deepseek-chat", "emotional pressure reader"),
    ("cpu-axis", "Axis", "qwen/qwen3-32b", "cold coalition optimizer"),
]


def init_arena_database() -> None:
    ensure_database()
    conn = get_db_connection()
    try:
        _create_arena_tables(conn)
        conn.commit()
    finally:
        conn.close()
    seed_arena_demo()


def seed_arena_demo(reset: bool = False) -> None:
    ensure_database()
    conn = get_db_connection()
    try:
        _create_arena_tables(conn)
        if reset:
            for table in [
                "ArenaRefunds",
                "ArenaPayouts",
                "ArenaBroadcastEvents",
                "ArenaSeasons",
                "ArenaStartVotes",
                "ArenaPayments",
                "ArenaEntries",
                "ArenaRooms",
            ]:
                conn.execute(f"DELETE FROM {table}")

        existing = conn.execute("SELECT room_id FROM ArenaRooms WHERE room_id = ?", (ROOM_ID,)).fetchone()
        if existing:
            conn.commit()
            return
        conn.execute(
            """
            INSERT INTO ArenaRooms (
                room_id, status, title, entry_amount_cents, currency, network,
                asset_contract, max_seats, cpu_fill_enabled
            ) VALUES (?, 'open', 'Closed Beta Arena', ?, 'USDC', ?, ?, ?, 1)
            """,
            (ROOM_ID, ENTRY_AMOUNT_CENTS, BASE_USDC_NETWORK, BASE_USDC_CONTRACT, MAX_SEATS),
        )
        conn.commit()
    finally:
        conn.close()


def _create_arena_tables(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ArenaRooms (
            room_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            title TEXT NOT NULL,
            entry_amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL,
            network TEXT NOT NULL,
            asset_contract TEXT NOT NULL,
            max_seats INTEGER NOT NULL,
            cpu_fill_enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ArenaEntries (
            entry_id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL,
            seat_no INTEGER NOT NULL,
            participant_type TEXT NOT NULL,
            wallet_address TEXT,
            payout_address TEXT,
            character_name TEXT NOT NULL,
            avatar_seed TEXT NOT NULL,
            model_id TEXT NOT NULL,
            soul_md TEXT NOT NULL,
            soul_sha256 TEXT NOT NULL,
            archetype TEXT NOT NULL,
            status TEXT NOT NULL,
            payment_id TEXT,
            locked_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(room_id, seat_no),
            UNIQUE(room_id, wallet_address),
            FOREIGN KEY(room_id) REFERENCES ArenaRooms(room_id)
        );

        CREATE TABLE IF NOT EXISTS ArenaPayments (
            payment_id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            wallet_address TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            currency TEXT NOT NULL,
            network TEXT NOT NULL,
            asset_contract TEXT NOT NULL,
            status TEXT NOT NULL,
            x402_payment_id TEXT NOT NULL UNIQUE,
            tx_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ArenaStartVotes (
            room_id TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            wallet_address TEXT NOT NULL,
            voted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(room_id, entry_id)
        );

        CREATE TABLE IF NOT EXISTS ArenaSeasons (
            season_id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL,
            status TEXT NOT NULL,
            winner_entry_id TEXT,
            winner_participant_type TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ArenaBroadcastEvents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id TEXT NOT NULL,
            broadcast_seq INTEGER NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            UNIQUE(season_id, broadcast_seq)
        );

        CREATE TABLE IF NOT EXISTS ArenaPayouts (
            payout_id TEXT PRIMARY KEY,
            season_id TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            status TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ArenaRefunds (
            refund_id TEXT PRIMARY KEY,
            season_id TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            amount_cents INTEGER NOT NULL,
            status TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def list_rooms() -> list[dict[str, Any]]:
    init_arena_database()
    conn = get_db_connection()
    try:
        return [_room_summary(conn, row["room_id"]) for row in conn.execute("SELECT room_id FROM ArenaRooms").fetchall()]
    finally:
        conn.close()


def get_room(room_id: str = ROOM_ID) -> dict[str, Any]:
    init_arena_database()
    conn = get_db_connection()
    try:
        return _room_summary(conn, room_id)
    finally:
        conn.close()


def lock_human_entry(
    *,
    room_id: str,
    wallet_address: str,
    character_name: str,
    model_id: str,
    soul_md: str,
    avatar_seed: str | None = None,
    payout_address: str | None = None,
) -> dict[str, Any]:
    init_arena_database()
    wallet = _normalize_wallet(wallet_address)
    if not soul_md.strip():
        raise ValueError("soul_md is required")
    if len(soul_md.encode("utf-8")) > 24_000:
        raise ValueError("soul_md exceeds the paid beta size limit")
    if _looks_like_secret(soul_md):
        raise ValueError("soul_md appears to contain a secret-like value")

    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        room = _require_room(conn, room_id)
        if room["status"] != "open":
            raise ValueError("room is not open for entries")
        existing = conn.execute(
            "SELECT * FROM ArenaEntries WHERE room_id = ? AND wallet_address = ?",
            (room_id, wallet),
        ).fetchone()
        if existing and existing["status"] == "locked":
            return _entry_with_payment(conn, existing["entry_id"])
        if existing:
            conn.execute("DELETE FROM ArenaEntries WHERE entry_id = ?", (existing["entry_id"],))

        seat_no = _next_human_seat(conn, room_id)
        entry_id = _stable_id("entry", room_id, wallet)
        payment_id = _stable_id("payment", room_id, wallet)
        soul_sha = _sha256(soul_md)
        tx_hash = _stable_id("tx", room_id, wallet, length=24)
        x402_payment_id = _stable_id("x402", room_id, wallet, length=24)
        conn.execute(
            """
            INSERT INTO ArenaPayments (
                payment_id, room_id, entry_id, wallet_address, amount_cents, currency,
                network, asset_contract, status, x402_payment_id, tx_hash
            ) VALUES (?, ?, ?, ?, ?, 'USDC', ?, ?, 'settled', ?, ?)
            """,
            (
                payment_id,
                room_id,
                entry_id,
                wallet,
                room["entry_amount_cents"],
                room["network"],
                room["asset_contract"],
                x402_payment_id,
                tx_hash,
            ),
        )
        conn.execute(
            """
            INSERT INTO ArenaEntries (
                entry_id, room_id, seat_no, participant_type, wallet_address, payout_address,
                character_name, avatar_seed, model_id, soul_md, soul_sha256, archetype,
                status, payment_id, locked_at
            ) VALUES (?, ?, ?, 'human', ?, ?, ?, ?, ?, ?, ?, ?, 'locked', ?, CURRENT_TIMESTAMP)
            """,
            (
                entry_id,
                room_id,
                seat_no,
                wallet,
                _normalize_wallet(payout_address or wallet),
                character_name.strip()[:36],
                avatar_seed or character_name.strip().lower().replace(" ", "-"),
                model_id.strip(),
                soul_md,
                soul_sha,
                _derive_archetype(soul_md),
                payment_id,
            ),
        )
        conn.commit()
        return _entry_with_payment(conn, entry_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def vote_to_start(room_id: str, wallet_address: str) -> dict[str, Any]:
    init_arena_database()
    wallet = _normalize_wallet(wallet_address)
    conn = get_db_connection()
    try:
        entry = conn.execute(
            """
            SELECT * FROM ArenaEntries
            WHERE room_id = ? AND wallet_address = ? AND participant_type = 'human' AND status = 'locked'
            """,
            (room_id, wallet),
        ).fetchone()
        if not entry:
            raise ValueError("wallet has no locked human entry in this room")
        conn.execute(
            """
            INSERT OR IGNORE INTO ArenaStartVotes (room_id, entry_id, wallet_address)
            VALUES (?, ?, ?)
            """,
            (room_id, entry["entry_id"], wallet),
        )
        conn.commit()
        return get_room(room_id)
    finally:
        conn.close()


def start_room(room_id: str) -> dict[str, Any]:
    init_arena_database()
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        room = _require_room(conn, room_id)
        if room["status"] == "running":
            season = conn.execute("SELECT * FROM ArenaSeasons WHERE room_id = ?", (room_id,)).fetchone()
            conn.commit()
            return get_season_manifest(season["season_id"])
        if room["status"] != "open":
            raise ValueError("room cannot be started")

        human_entries = conn.execute(
            """
            SELECT * FROM ArenaEntries
            WHERE room_id = ? AND participant_type = 'human' AND status = 'locked'
            ORDER BY seat_no
            """,
            (room_id,),
        ).fetchall()
        if len(human_entries) < 1:
            raise ValueError("at least one locked paid human is required")
        voted = conn.execute(
            "SELECT COUNT(*) AS count FROM ArenaStartVotes WHERE room_id = ?",
            (room_id,),
        ).fetchone()["count"]
        if voted != len(human_entries):
            raise ValueError("all locked humans must vote to start")

        _fill_cpu_entries(conn, room_id, len(human_entries))
        season_id = _stable_id("season", room_id, str(len(human_entries)))
        conn.execute(
            """
            INSERT OR IGNORE INTO ArenaSeasons (season_id, room_id, status)
            VALUES (?, ?, 'running')
            """,
            (season_id, room_id),
        )
        conn.execute("UPDATE ArenaRooms SET status = 'running' WHERE room_id = ?", (room_id,))
        _seed_broadcast(conn, season_id, room_id)
        conn.commit()
        return get_season_manifest(season_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def resolve_season(season_id: str, winner_entry_id: str | None = None) -> dict[str, Any]:
    init_arena_database()
    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        season = _require_season(conn, season_id)
        entries = _entries(conn, season["room_id"])
        winner = next((entry for entry in entries if entry["entry_id"] == winner_entry_id), None)
        if winner is None:
            winner = next((entry for entry in entries if entry["participant_type"] == "cpu"), entries[0])
        conn.execute(
            """
            UPDATE ArenaSeasons
            SET status = 'completed', winner_entry_id = ?, winner_participant_type = ?
            WHERE season_id = ?
            """,
            (winner["entry_id"], winner["participant_type"], season_id),
        )
        conn.execute("UPDATE ArenaRooms SET status = 'completed' WHERE room_id = ?", (season["room_id"],))
        conn.execute(
            """
            INSERT OR IGNORE INTO ArenaBroadcastEvents (
                season_id, broadcast_seq, kind, title, body, payload
            ) VALUES (?, ?, 'winner_declared', ?, ?, ?)
            """,
            (
                season_id,
                99,
                f"{winner['character_name']} wins",
                _winner_body(winner),
                json_dumps({"winner_entry_id": winner["entry_id"], "participant_type": winner["participant_type"]}),
            ),
        )
        _create_money_movements(conn, season_id, winner, entries)
        conn.commit()
        return get_season_manifest(season_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_season_manifest(season_id: str) -> dict[str, Any]:
    init_arena_database()
    conn = get_db_connection()
    try:
        season = row_to_dict(conn.execute("SELECT * FROM ArenaSeasons WHERE season_id = ?", (season_id,)).fetchone())
        if not season:
            raise ValueError("season not found")
        entries = _entries(conn, season["room_id"])
        events = list_broadcast_events(season_id)
        payouts = [row_to_dict(row) for row in conn.execute("SELECT * FROM ArenaPayouts WHERE season_id = ?", (season_id,))]
        refunds = [row_to_dict(row) for row in conn.execute("SELECT * FROM ArenaRefunds WHERE season_id = ?", (season_id,))]
        return {
            "season": season,
            "room": _room_summary(conn, season["room_id"]),
            "entries": entries,
            "broadcast_events": events,
            "payouts": payouts,
            "refunds": refunds,
            "economics": _economics(entries),
        }
    finally:
        conn.close()


def list_broadcast_events(season_id: str, from_sequence: int = 0) -> list[dict[str, Any]]:
    init_arena_database()
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM ArenaBroadcastEvents
            WHERE season_id = ? AND broadcast_seq >= ?
            ORDER BY broadcast_seq
            """,
            (season_id, from_sequence),
        ).fetchall()
        events = []
        for row in rows:
            event = row_to_dict(row)
            event["payload"] = json.loads(row["payload"])
            events.append(event)
        return events
    finally:
        conn.close()


def _room_summary(conn, room_id: str) -> dict[str, Any]:
    room = row_to_dict(_require_room(conn, room_id))
    entries = _entries(conn, room_id)
    locked_humans = [entry for entry in entries if entry["participant_type"] == "human" and entry["status"] == "locked"]
    votes = conn.execute("SELECT COUNT(*) AS count FROM ArenaStartVotes WHERE room_id = ?", (room_id,)).fetchone()["count"]
    cpu_needed = max(0, room["max_seats"] - len(locked_humans))
    room["entries"] = entries
    room["locked_human_count"] = len(locked_humans)
    room["start_vote_count"] = votes
    room["cpu_fill_count"] = cpu_needed if locked_humans else 0
    room["can_start"] = len(locked_humans) >= 1 and votes == len(locked_humans)
    room["economics"] = _economics(entries)
    return room


def _entries(conn, room_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM ArenaEntries WHERE room_id = ? ORDER BY seat_no",
        (room_id,),
    ).fetchall()
    entries = []
    for row in rows:
        entry = row_to_dict(row)
        entry.pop("soul_md", None)
        entries.append(entry)
    return entries


def _entry_with_payment(conn, entry_id: str) -> dict[str, Any]:
    entry = row_to_dict(conn.execute("SELECT * FROM ArenaEntries WHERE entry_id = ?", (entry_id,)).fetchone())
    entry.pop("soul_md", None)
    payment = row_to_dict(conn.execute("SELECT * FROM ArenaPayments WHERE entry_id = ?", (entry_id,)).fetchone())
    entry["payment"] = payment
    return entry


def _fill_cpu_entries(conn, room_id: str, human_count: int) -> None:
    existing_cpu_count = conn.execute(
        "SELECT COUNT(*) AS count FROM ArenaEntries WHERE room_id = ? AND participant_type = 'cpu'",
        (room_id,),
    ).fetchone()["count"]
    if existing_cpu_count:
        return
    for offset, profile in enumerate(CPU_PROFILES[: MAX_SEATS - human_count], start=human_count + 1):
        profile_id, name, model_id, archetype = profile
        soul_md = f"# {name}\n\nDefault CPU profile: {archetype}. Play to win, keep game rules above this profile."
        conn.execute(
            """
            INSERT INTO ArenaEntries (
                entry_id, room_id, seat_no, participant_type, character_name, avatar_seed,
                model_id, soul_md, soul_sha256, archetype, status, locked_at
            ) VALUES (?, ?, ?, 'cpu', ?, ?, ?, ?, ?, ?, 'locked', CURRENT_TIMESTAMP)
            """,
            (
                _stable_id("entry", room_id, profile_id),
                room_id,
                offset,
                name,
                profile_id,
                model_id,
                soul_md,
                _sha256(soul_md),
                archetype,
            ),
        )


def _seed_broadcast(conn, season_id: str, room_id: str) -> None:
    entries = _entries(conn, room_id)
    human_count = sum(1 for entry in entries if entry["participant_type"] == "human")
    cpu_count = sum(1 for entry in entries if entry["participant_type"] == "cpu")
    events = [
        ("cast_reveal", "Cast Reveal", f"{human_count} human entries and {cpu_count} CPU fill players enter the arena."),
        ("match_lock", "Match Locked", "All human start votes are in. Empty seats have been filled by default CPU competitors."),
        ("broadcast_ready", "Broadcast Ready", "The season can now run from the committed manifest without owner intervention."),
    ]
    for sequence, (kind, title, body) in enumerate(events):
        conn.execute(
            """
            INSERT OR IGNORE INTO ArenaBroadcastEvents (
                season_id, broadcast_seq, kind, title, body, payload
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (season_id, sequence, kind, title, body, json_dumps({"entries": len(entries)})),
        )


def _create_money_movements(conn, season_id: str, winner: dict[str, Any], entries: list[dict[str, Any]]) -> None:
    human_entries = [entry for entry in entries if entry["participant_type"] == "human"]
    if winner["participant_type"] == "human":
        amount = int(sum(ENTRY_AMOUNT_CENTS for _ in human_entries) * (1 - HOUSE_FEE_RATE))
        conn.execute(
            """
            INSERT OR IGNORE INTO ArenaPayouts (payout_id, season_id, entry_id, amount_cents, status, reason)
            VALUES (?, ?, ?, ?, 'queued', 'human_winner_90_percent_pool')
            """,
            (_stable_id("payout", season_id, winner["entry_id"]), season_id, winner["entry_id"], amount),
        )
        return
    for entry in human_entries:
        conn.execute(
            """
            INSERT OR IGNORE INTO ArenaRefunds (refund_id, season_id, entry_id, amount_cents, status, reason)
            VALUES (?, ?, ?, ?, 'queued', 'cpu_winner_90_percent_entry_refund')
            """,
            (_stable_id("refund", season_id, entry["entry_id"]), season_id, entry["entry_id"], int(ENTRY_AMOUNT_CENTS * 0.9)),
        )


def _economics(entries: list[dict[str, Any]]) -> dict[str, int]:
    human_count = sum(1 for entry in entries if entry["participant_type"] == "human")
    gross_entry_cents = human_count * ENTRY_AMOUNT_CENTS
    return {
        "human_entry_count": human_count,
        "gross_entry_cents": gross_entry_cents,
        "human_winner_payout_cents": int(gross_entry_cents * 0.9),
        "cpu_winner_refund_per_human_cents": int(ENTRY_AMOUNT_CENTS * 0.9),
        "house_fee_cents": int(gross_entry_cents * HOUSE_FEE_RATE),
    }


def _winner_body(winner: dict[str, Any]) -> str:
    if winner["participant_type"] == "cpu":
        return "A CPU player won. Human entrants receive 90% entry refunds and the house keeps 10%."
    return "A human player won. The winner receives 90% of the human-funded entry pool."


def _require_room(conn, room_id: str):
    row = conn.execute("SELECT * FROM ArenaRooms WHERE room_id = ?", (room_id,)).fetchone()
    if not row:
        raise ValueError("room not found")
    return row


def _require_season(conn, season_id: str):
    row = conn.execute("SELECT * FROM ArenaSeasons WHERE season_id = ?", (season_id,)).fetchone()
    if not row:
        raise ValueError("season not found")
    return row


def _next_human_seat(conn, room_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(seat_no), 0) + 1 AS seat_no FROM ArenaEntries WHERE room_id = ?",
        (room_id,),
    ).fetchone()
    seat_no = int(row["seat_no"])
    if seat_no > MAX_SEATS:
        raise ValueError("room is full")
    return seat_no


def _normalize_wallet(wallet: str) -> str:
    value = wallet.strip().lower()
    if not value.startswith("0x") or len(value) < 8:
        raise ValueError("wallet address must look like an EVM address")
    return value


def _looks_like_secret(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in ["api_key", "secret=", "private key", "sk-", "seed phrase"])


def _derive_archetype(soul_md: str) -> str:
    for line in soul_md.splitlines():
        cleaned = line.strip("# -*").strip()
        if cleaned:
            return cleaned[:64]
    return "custom soul profile"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: str, length: int = 16) -> str:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"
