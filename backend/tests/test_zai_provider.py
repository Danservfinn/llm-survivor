from __future__ import annotations

import json
import os
import unittest
from unittest.mock import Mock, patch

from backend import llm_config
from backend import model_rosters
from backend import openrouter_client
from backend.api import AutoRunToEndRequest


class ZAIProviderTest(unittest.TestCase):
    def test_auto_run_to_end_request_accepts_frontend_turn_budget(self) -> None:
        request = AutoRunToEndRequest(max_rounds=16, max_turns=1200, max_live_calls=1000, max_estimated_cost_cents=500)

        self.assertEqual(request.max_turns, 1200)

    def test_zai_roster_preset_is_available_and_seedable(self) -> None:
        rosters = model_rosters.list_model_rosters()
        zai_roster = next(roster for roster in rosters if roster["id"] == "zai_glm")
        agents = model_rosters.agents_for_roster("zai_glm")

        self.assertEqual(zai_roster["name"], "Z.ai GLM Smoke Roster")
        self.assertEqual(len(agents), len(zai_roster["models"]))
        self.assertTrue(all(agent["model_id"] == "glm-4.5-flash" for agent in agents))
        self.assertIn("GLM Flash Alpha", [agent["pseudonym"] for agent in agents])

    def test_zai_key_enables_live_provider(self) -> None:
        with patch.dict(os.environ, {"LLM_PROVIDER": "zai", "ZAI_API_KEY": "test-key"}, clear=True):
            settings = llm_config.get_llm_settings()
            self.assertEqual(settings.provider, "zai")
            self.assertTrue(settings.zai_configured)
            self.assertTrue(llm_config.should_use_live_llm())
            self.assertEqual(llm_config.live_llm_provider(), "zai")

    def test_zai_chat_uses_openai_compatible_endpoint_and_key(self) -> None:
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = json.dumps(
            {"choices": [{"message": {"content": '{"archetype":"vote broker"}'}}]}
        ).encode("utf-8")

        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "zai", "ZAI_API_KEY": "test-key", "ZAI_BASE_URL": "https://example.test/v4"},
            clear=True,
        ), patch("backend.openrouter_client.urllib.request.urlopen", return_value=response) as urlopen:
            payload = {
                "model": "glm-4.5-flash",
                "messages": [{"role": "user", "content": "Return JSON"}],
                "temperature": 0.2,
                "max_tokens": 20,
                "_response_format": "json",
            }
            result = openrouter_client._post_chat_completion(payload, None)

        self.assertEqual(result["choices"][0]["message"]["content"], '{"archetype":"vote broker"}')
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/v4/chat/completions")
        self.assertEqual(request.headers["Authorization"], "Bearer test-key")
        outbound_payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(outbound_payload["model"], "glm-4.5-flash")
        self.assertNotIn("_response_format", outbound_payload)


if __name__ == "__main__":
    unittest.main()
