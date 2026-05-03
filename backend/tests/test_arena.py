from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend import arena, database


class ArenaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DATABASE_PATH = Path(self.temp_dir.name) / "survivor.db"
        database.seed_demo(reset=True)
        arena.seed_arena_demo(reset=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def lock_entry(self, wallet: str = "0xabc12345"):
        return arena.lock_human_entry(
            room_id=arena.ROOM_ID,
            wallet_address=wallet,
            character_name="Human Prime",
            model_id="openai/gpt-4.1",
            soul_md="# Human Prime\n\nWin with calm social play.",
        )

    def test_one_human_can_start_with_cpu_fill(self) -> None:
        entry = self.lock_entry()
        arena.vote_to_start(arena.ROOM_ID, entry["wallet_address"])

        manifest = arena.start_room(arena.ROOM_ID)
        entries = manifest["entries"]

        self.assertEqual(len(entries), 16)
        self.assertEqual(sum(1 for entry in entries if entry["participant_type"] == "human"), 1)
        self.assertEqual(sum(1 for entry in entries if entry["participant_type"] == "cpu"), 15)
        self.assertEqual(manifest["season"]["status"], "running")

    def test_all_locked_humans_must_vote_to_start(self) -> None:
        first = self.lock_entry("0xabc12345")
        self.lock_entry("0xdef67890")
        arena.vote_to_start(arena.ROOM_ID, first["wallet_address"])

        with self.assertRaisesRegex(ValueError, "all locked humans"):
            arena.start_room(arena.ROOM_ID)

    def test_cpu_winner_refunds_humans_minus_house_fee(self) -> None:
        human = self.lock_entry()
        arena.vote_to_start(arena.ROOM_ID, human["wallet_address"])
        manifest = arena.start_room(arena.ROOM_ID)
        cpu_winner = next(entry for entry in manifest["entries"] if entry["participant_type"] == "cpu")

        resolved = arena.resolve_season(manifest["season"]["season_id"], cpu_winner["entry_id"])

        self.assertEqual(resolved["season"]["winner_participant_type"], "cpu")
        self.assertEqual(len(resolved["refunds"]), 1)
        self.assertEqual(resolved["refunds"][0]["amount_cents"], 2250)
        self.assertEqual(resolved["payouts"], [])

    def test_human_winner_gets_ninety_percent_pool_payout(self) -> None:
        human = self.lock_entry()
        arena.vote_to_start(arena.ROOM_ID, human["wallet_address"])
        manifest = arena.start_room(arena.ROOM_ID)

        resolved = arena.resolve_season(manifest["season"]["season_id"], human["entry_id"])

        self.assertEqual(resolved["season"]["winner_participant_type"], "human")
        self.assertEqual(len(resolved["payouts"]), 1)
        self.assertEqual(resolved["payouts"][0]["amount_cents"], 2250)
        self.assertEqual(resolved["refunds"], [])

    def test_cpu_entries_do_not_have_payment_or_wallet(self) -> None:
        human = self.lock_entry()
        arena.vote_to_start(arena.ROOM_ID, human["wallet_address"])
        manifest = arena.start_room(arena.ROOM_ID)

        cpu_entries = [entry for entry in manifest["entries"] if entry["participant_type"] == "cpu"]
        self.assertTrue(cpu_entries)
        self.assertTrue(all(entry["payment_id"] is None for entry in cpu_entries))
        self.assertTrue(all(entry["wallet_address"] is None for entry in cpu_entries))


if __name__ == "__main__":
    unittest.main()
