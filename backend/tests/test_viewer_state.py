from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend import database, turn_controller
from backend.viewer_state import get_viewer_state, update_viewer_state


class ViewerStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DATABASE_PATH = Path(self.temp_dir.name) / "survivor.db"
        database.seed_demo(reset=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_seeded_viewer_state_starts_at_first_replay_beat(self) -> None:
        state = get_viewer_state()

        self.assertEqual(state["round"], 7)
        self.assertEqual(state["phase"], "round")
        self.assertEqual(state["replay_index"], 0)
        self.assertFalse(state["is_playing"])

    def test_viewer_state_is_in_shared_api_state(self) -> None:
        turn_controller.auto_run(3)
        update_viewer_state(replay_index=2, is_playing=True)

        state = turn_controller.get_state()

        self.assertEqual(state["viewer_state"]["replay_index"], 2)
        self.assertTrue(state["viewer_state"]["is_playing"])

    def test_viewer_state_clamps_to_existing_story_events(self) -> None:
        turn_controller.auto_run(3)

        state = update_viewer_state(replay_index=99, is_playing=True)

        self.assertEqual(state["replay_index"], 2)
        self.assertTrue(state["is_playing"])

    def test_reset_clears_viewer_state(self) -> None:
        turn_controller.auto_run(3)
        update_viewer_state(replay_index=2, is_playing=True)

        database.seed_demo(reset=True)
        state = get_viewer_state()

        self.assertEqual(state["replay_index"], 0)
        self.assertFalse(state["is_playing"])


if __name__ == "__main__":
    unittest.main()
