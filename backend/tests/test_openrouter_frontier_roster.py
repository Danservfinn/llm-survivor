from __future__ import annotations

import unittest

from backend.fixtures import DEMO_AGENTS


class OpenRouterFrontierRosterTest(unittest.TestCase):
    def test_default_roster_is_sixteen_current_openrouter_frontier_models(self) -> None:
        expected = [
            ("GPT-5.5 Pro", "openai/gpt-5.5-pro"),
            ("Claude Opus 4.8", "anthropic/claude-opus-4.8"),
            ("Gemini 3.1 Pro Preview", "google/gemini-3.1-pro-preview"),
            ("Grok 4.3", "x-ai/grok-4.3"),
            ("DeepSeek V4 Pro", "deepseek/deepseek-v4-pro"),
            ("Qwen3.7 Max", "qwen/qwen3.7-max"),
            ("GLM 5.2", "z-ai/glm-5.2"),
            ("Kimi K2.7 Code", "moonshotai/kimi-k2.7-code"),
            ("MiniMax M3", "minimax/minimax-m3"),
            ("Nemotron 3 Ultra", "nvidia/nemotron-3-ultra-550b-a55b"),
            ("Mistral Large 3 2512", "mistralai/mistral-large-2512"),
            ("Llama 4 Maverick", "meta-llama/llama-4-maverick"),
            ("Command A", "cohere/command-a"),
            ("Gemma 4 31B", "google/gemma-4-31b-it"),
            ("Granite 4.1 8B", "ibm-granite/granite-4.1-8b"),
            ("Reka Edge", "rekaai/reka-edge"),
        ]

        actual = [(agent["pseudonym"], agent["model_id"]) for agent in DEMO_AGENTS]

        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 16)
        self.assertEqual(len({model_id for _, model_id in actual}), 16)
        self.assertTrue(all("/" in model_id for _, model_id in actual))
