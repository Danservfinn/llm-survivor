from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend import api


class ApiStaticServingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.frontend_dist = Path(self.temp_dir.name) / "out"
        self.frontend_dist.mkdir()
        (self.frontend_dist / "index.html").write_text("<main>LLM Survivor</main>", encoding="utf-8")
        (self.frontend_dist / "benchmark.html").write_text("<main>Benchmark</main>", encoding="utf-8")
        nested = self.frontend_dist / "arena"
        nested.mkdir()
        (nested / "index.html").write_text("<main>Arena</main>", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_resolves_frontend_files_and_falls_back_to_index(self) -> None:
        with patch.object(api, "FRONTEND_DIST", self.frontend_dist):
            self.assertEqual(api._resolve_frontend_file("").name, "index.html")
            self.assertEqual(api._resolve_frontend_file("benchmark").name, "benchmark.html")
            self.assertEqual(api._resolve_frontend_file("arena").name, "index.html")
            self.assertEqual(api._resolve_frontend_file("unknown-route").name, "index.html")

    def test_rejects_api_media_and_unsafe_paths(self) -> None:
        with patch.object(api, "FRONTEND_DIST", self.frontend_dist):
            self.assertIsNone(api._resolve_frontend_file("api/state"))
            self.assertIsNone(api._resolve_frontend_file("media/voice/test.wav"))
            with self.assertRaises(HTTPException):
                api._resolve_frontend_file("../secret")

    def test_returns_none_when_no_frontend_build_exists(self) -> None:
        missing_dist = Path(self.temp_dir.name) / "missing"
        with patch.object(api, "FRONTEND_DIST", missing_dist):
            self.assertIsNone(api._resolve_frontend_file("benchmark"))

    def test_mounts_next_assets_and_voice_media(self) -> None:
        mounted_paths = {route.path for route in api.app.routes}

        self.assertIn("/_next", mounted_paths)
        self.assertIn("/media/voice", mounted_paths)


if __name__ == "__main__":
    unittest.main()
