from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend import database, round_preloader, turn_controller


class RoundPreloaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DATABASE_PATH = Path(self.temp_dir.name) / "survivor.db"
        database.seed_demo(reset=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_preload_generates_next_round_buffer_without_advancing_replay(self) -> None:
        turn_controller.auto_run(40)
        before = turn_controller.get_state()

        status = round_preloader.start_next_round_preload(run_inline=True)
        after = turn_controller.get_state()

        self.assertEqual(status["status"], "complete")
        self.assertEqual(status["source_round"], 7)
        self.assertEqual(status["target_round"], 8)
        self.assertEqual(status["provider"], "deterministic")
        self.assertEqual(status["event_count"], 6)
        self.assertEqual(before["game"], after["game"])
        self.assertEqual(before["turn_count"], after["turn_count"])
        self.assertEqual(before["story_event_count"], after["story_event_count"])
        self.assertEqual(after["next_round_preload"]["status"], "complete")

    def test_state_exposes_preload_status_without_raw_responses(self) -> None:
        turn_controller.auto_run(40)
        round_preloader.start_next_round_preload(run_inline=True)

        state = turn_controller.get_state()
        state_text = json.dumps(state)
        preload = state["next_round_preload"]

        self.assertEqual(preload["target_round"], 8)
        self.assertIn("agent_response_count", preload["context_digest"])
        self.assertNotIn("agent_responses", state_text)
        self.assertNotIn("host_response", state_text)
        self.assertNotIn("generated_payload", state_text)

    def test_repeated_preload_start_reuses_completed_buffer(self) -> None:
        turn_controller.auto_run(40)
        first = round_preloader.start_next_round_preload(run_inline=True)
        second = round_preloader.start_next_round_preload(run_inline=True)

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["status"], "complete")


if __name__ == "__main__":
    unittest.main()
