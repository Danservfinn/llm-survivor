from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import database, turn_controller, voice_service
from backend.voice_config import VoiceConfigurationError, redact_secrets


class VoiceServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        database.DATABASE_PATH = root / "survivor.db"
        voice_service.MEDIA_ROOT = root / "media" / "voice"
        database.seed_demo(reset=True)
        turn_controller.auto_run(40)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_fake_provider_builds_voice_without_api_key(self) -> None:
        with patch.dict(os.environ, {"VOICE_PROVIDER": "fake", "ELEVENLABS_API_KEY": ""}, clear=False):
            result = voice_service.build_episode_voice(round_number=7, phase="tribal")

        self.assertEqual(result["provider"], "fake")
        self.assertGreater(result["line_count"], 0)
        self.assertEqual(result["statuses"].get("failed", 0), 0)
        self.assertGreater(result["statuses"].get("ready", 0), 0)

    def test_elevenlabs_provider_requires_backend_env_key(self) -> None:
        with patch.dict(os.environ, {"VOICE_PROVIDER": "elevenlabs", "ELEVENLABS_API_KEY": ""}, clear=False):
            with self.assertRaises(VoiceConfigurationError) as raised:
                voice_service.build_episode_voice(round_number=7, phase="tribal")

        self.assertIn("ELEVENLABS_API_KEY", str(raised.exception))
        self.assertNotIn("sk_", str(raised.exception))

    def test_episode_audio_payload_has_public_timeline_without_secret_material(self) -> None:
        with patch.dict(os.environ, {"VOICE_PROVIDER": "fake"}, clear=False):
            voice_service.build_episode_voice(round_number=7, phase="tribal")

        episode = turn_controller.get_episode(round_number=7, phase="tribal", include_audio=True)
        payload_text = json.dumps(episode)
        voiced_events = [
            event for event in episode["events"] if event["payload"].get("voice_timeline")
        ]

        self.assertEqual(len(voiced_events), len(episode["events"]))
        self.assertNotIn("ELEVENLABS_API_KEY", payload_text)
        self.assertNotIn("sk_", payload_text)
        self.assertNotIn("voice_id", payload_text)

    def test_voice_timeline_never_overlaps_and_ordinary_gaps_are_bounded(self) -> None:
        with patch.dict(os.environ, {"VOICE_PROVIDER": "fake"}, clear=False):
            voice_service.build_episode_voice(round_number=7, phase="tribal")

        episode = turn_controller.get_episode(round_number=7, phase="tribal", include_audio=True)
        for event in episode["events"]:
            timeline = event["payload"]["voice_timeline"]
            self.assertEqual(timeline[0]["speaker_id"], "host")
            for previous, current in zip(timeline, timeline[1:]):
                self.assertGreaterEqual(current["start_ms"], previous["end_ms"])
                gap = current["start_ms"] - previous["end_ms"]
                self.assertLessEqual(gap, 900)

    def test_redaction_masks_pasted_key_shape(self) -> None:
        redacted = redact_secrets("failed with sk_1234567890abcdef1234567890abcdef")

        self.assertNotIn("sk_1234567890abcdef", redacted)
        self.assertIn("[REDACTED]", redacted)


if __name__ == "__main__":
    unittest.main()
