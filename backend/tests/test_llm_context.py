from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import database, openrouter_client, turn_controller
from backend.llm_context import build_agent_episode_context, build_host_episode_context
from backend.openrouter_client import AgentAction, HostNarration


class LLMContextBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}, clear=False)
        self.env_patch.start()
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DATABASE_PATH = Path(self.temp_dir.name) / "survivor.db"
        database.seed_demo(reset=True)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_agent_context_includes_public_events_and_own_private_memory(self) -> None:
        turn_controller.auto_run(20)
        conn = database.get_db_connection()
        try:
            context = build_agent_episode_context(
                conn,
                actor_id="agent-bravo",
                round_number=7,
                current_step="vote_booth_agent-bravo",
            )
        finally:
            conn.close()

        public_text = json.dumps(context["public_timeline"])
        private_text = json.dumps(context["actor_private_memory"])
        full_text = json.dumps(context)

        self.assertIn("Night 7 | Tribal Conference", public_text)
        self.assertIn("Camp | The Quiet Count", public_text)
        self.assertIn("I am trying to keep two alliances", private_text)
        self.assertIn("I am privately weighing", private_text)
        self.assertNotIn("Grok 4.3 knows the room is tilted", full_text)
        self.assertNotIn("People are smiling too much", full_text)

    def test_agent_vote_context_excludes_hidden_prior_vote_targets(self) -> None:
        turn_controller.auto_run(22)
        conn = database.get_db_connection()
        try:
            context = build_agent_episode_context(
                conn,
                actor_id="agent-cipher",
                round_number=7,
                current_step="vote_booth_agent-cipher",
            )
        finally:
            conn.close()

        public_kinds = {event["kind"] for event in context["public_timeline"]}
        private_vote_entries = [
            event
            for event in context["actor_private_memory"]
            if event.get("kind") == "vote_booth"
        ]

        self.assertNotIn("vote_booth", public_kinds)
        self.assertEqual(private_vote_entries, [])
        self.assertEqual(context["visible_game_state"]["revealed_vote_tally"], {})

    def test_host_context_includes_private_material_but_redacts_unrevealed_votes(self) -> None:
        turn_controller.auto_run(25)
        conn = database.get_db_connection()
        try:
            context = build_host_episode_context(
                conn,
                round_number=7,
                current_step="vote_booth_agent-cipher",
            )
        finally:
            conn.close()

        host_timeline = context["host_timeline"]
        host_text = json.dumps(host_timeline)
        vote_entries = [event for event in host_timeline if event["kind"] == "vote_booth"]
        kinds = {event["kind"] for event in host_timeline}

        self.assertIn("I am privately weighing", host_text)
        self.assertNotIn("vote_reveal", kinds)
        self.assertNotIn("elimination", kinds)
        self.assertGreater(len(vote_entries), 0)
        for event in vote_entries:
            self.assertIn("Target hidden until reveal", event["dialogue"])
            self.assertNotIn("target_ids", event)
            self.assertNotIn("subtitle", event)
            self.assertNotIn("private_thought", event)


class OpenRouterPromptContextTest(unittest.TestCase):
    def test_agent_prompt_contains_episode_context(self) -> None:
        calls: list[dict] = []

        def fake_post(payload: dict, api_key: str) -> dict:
            calls.append(payload)
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "dialogue": "I am carrying that earlier promise into this vote.",
                                    "inner_thought": "Prior Beat changed my path.",
                                    "target_id": "agent-delta",
                                }
                            )
                        }
                    }
                ]
            }

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            with patch("backend.openrouter_client._post_chat_completion", side_effect=fake_post):
                result = openrouter_client.request_agent_action(
                    actor={
                        "agent_id": "agent-bravo",
                        "pseudonym": "Claude Sonnet 4.5",
                        "model_id": "anthropic/claude-sonnet-4.5",
                        "archetype": "social connector",
                        "confessional_memory": "Keep promises from crossing.",
                    },
                    step="vote_booth_agent-bravo",
                    scene_context="Vote now.",
                    allowed_targets=[
                        {
                            "agent_id": "agent-delta",
                            "pseudonym": "Grok 4.3",
                            "archetype": "challenge threat",
                        }
                    ],
                    response_kind="vote",
                    episode_context={
                        "public_timeline": [{"title": "Prior Beat"}],
                        "actor_private_memory": [{"memory": "Private Beat"}],
                    },
                )

        prompt = calls[0]["messages"][1]["content"]
        self.assertEqual(result.target_id, "agent-delta")
        self.assertIn("Prior episode context visible to you", prompt)
        self.assertIn("public_timeline", prompt)
        self.assertIn("Prior Beat", prompt)
        self.assertIn("Private Beat", prompt)
        self.assertNotIn("Because <strategic cause>", prompt)
        self.assertNotIn("Risk:", prompt)
        self.assertNotIn("Intended outcome", prompt)
        self.assertNotIn("Your archetype", prompt)
        self.assertIn("written in first person", prompt)
        self.assertIn("not a narrator describing", prompt)
        self.assertEqual(result.inner_thought, "Prior Beat changed my path.")

    def test_agent_dialogue_strips_third_person_attribution(self) -> None:
        def fake_post(payload: dict, api_key: str) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "dialogue": "Claude Sonnet 4.5 says I need this vote to stay flexible.",
                                    "inner_thought": "Stay flexible.",
                                    "target_id": "agent-delta",
                                }
                            )
                        }
                    }
                ]
            }

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            with patch("backend.openrouter_client._post_chat_completion", side_effect=fake_post):
                result = openrouter_client.request_agent_action(
                    actor={
                        "agent_id": "agent-bravo",
                        "pseudonym": "Claude Sonnet 4.5",
                        "model_id": "anthropic/claude-sonnet-4.5",
                        "archetype": "social connector",
                        "confessional_memory": "",
                    },
                    step="camp_strategy",
                    scene_context="Camp strategy.",
                    allowed_targets=[
                        {
                            "agent_id": "agent-delta",
                            "pseudonym": "Grok 4.3",
                            "archetype": "challenge threat",
                        }
                    ],
                    response_kind="conversation",
                    episode_context={},
                )

        self.assertEqual(result.dialogue, "I need this vote to stay flexible.")

    def test_agent_inner_thought_rejects_self_third_person(self) -> None:
        def fake_post(payload: dict, api_key: str) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "dialogue": "I need this vote to stay flexible.",
                                    "inner_thought": "Claude Sonnet 4.5 is replaying the vote math.",
                                    "target_id": "agent-delta",
                                }
                            )
                        }
                    }
                ]
            }

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            with patch("backend.openrouter_client._post_chat_completion", side_effect=fake_post):
                result = openrouter_client.request_agent_action(
                    actor={
                        "agent_id": "agent-bravo",
                        "pseudonym": "Claude Sonnet 4.5",
                        "model_id": "anthropic/claude-sonnet-4.5",
                        "archetype": "social connector",
                        "confessional_memory": "",
                    },
                    step="exit_confessional",
                    scene_context="Exit confessional.",
                    allowed_targets=[],
                    response_kind="confessional",
                    episode_context={},
                )

        self.assertNotIn("Claude Sonnet 4.5", result.inner_thought)
        self.assertTrue(result.inner_thought.startswith("I "))

    def test_agent_prompt_keeps_model_reasoning_unstructured(self) -> None:
        def fake_post(payload: dict, api_key: str) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "dialogue": "I need this vote to loosen the majority.",
                                    "inner_thought": "Neutralize the threat.",
                                    "target_id": "agent-delta",
                                }
                            )
                        }
                    }
                ]
            }

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            with patch("backend.openrouter_client._post_chat_completion", side_effect=fake_post):
                result = openrouter_client.request_agent_action(
                    actor={
                        "agent_id": "agent-echo",
                        "pseudonym": "Llama 3.3 70B",
                        "model_id": "meta-llama/llama-3.3-70b-instruct",
                        "archetype": "quiet swing",
                        "confessional_memory": "Stay needed, stay hidden.",
                    },
                    step="vote_booth_agent-echo",
                    scene_context="Vote now.",
                    allowed_targets=[
                        {
                            "agent_id": "agent-delta",
                            "pseudonym": "Grok 4.3",
                            "archetype": "challenge threat",
                        }
                    ],
                    response_kind="vote",
                    episode_context={},
                )

        self.assertEqual(result.inner_thought, "Neutralize the threat.")

    def test_agent_request_does_not_substitute_default_model(self) -> None:
        calls: list[str] = []

        def fake_post(payload: dict, api_key: str) -> dict:
            calls.append(payload["model"])
            raise RuntimeError("model unavailable")

        with patch.dict(
            os.environ,
            {
                "OPENROUTER_API_KEY": "test-key",
                "OPENROUTER_DEFAULT_MODEL": "openai/gpt-4.1-mini",
            },
            clear=False,
        ):
            with patch("backend.openrouter_client._post_chat_completion", side_effect=fake_post):
                with self.assertRaises(RuntimeError):
                    openrouter_client.request_agent_action(
                        actor={
                            "agent_id": "agent-cipher",
                            "pseudonym": "Gemini 2.5 Pro",
                            "model_id": "google/gemini-2.5-pro",
                            "confessional_memory": "",
                        },
                        step="vote_booth_agent-cipher",
                        scene_context="Vote now.",
                        allowed_targets=[],
                        response_kind="vote",
                        episode_context={},
                    )

        self.assertEqual(calls, ["google/gemini-2.5-pro"])

    def test_host_prompt_contains_host_context(self) -> None:
        calls: list[dict] = []

        def fake_post(payload: dict, api_key: str) -> dict:
            calls.append(payload)
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "host_narration": "The earlier promise now shapes how this answer lands."
                                }
                            )
                        }
                    }
                ]
            }

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            with patch("backend.openrouter_client._post_chat_completion", side_effect=fake_post):
                result = openrouter_client.request_host_narration(
                    step="tribal_answer_trust",
                    event_outline={"title": "Llama 3.3 70B Answers"},
                    episode_context={
                        "host_timeline": [{"title": "Private Prior Beat"}],
                        "visibility": "host_omniscient_nonspoiling",
                    },
                )

        prompt = calls[0]["messages"][1]["content"]
        self.assertIn("Prior episode context available to the host", prompt)
        self.assertIn("Private Prior Beat", prompt)
        self.assertEqual(
            result.host_narration,
            "The earlier promise now shapes how this answer lands.",
        )


class TurnControllerLLMWiringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}, clear=False)
        self.env_patch.start()
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DATABASE_PATH = Path(self.temp_dir.name) / "survivor.db"
        database.seed_demo(reset=True)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_live_host_narration_is_stored_without_raw_context(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            with patch(
                "backend.turn_controller.request_host_narration",
                return_value=HostNarration("A context-aware host line lands here.", "test-host-model"),
            ):
                result = turn_controller.advance_turn()

        event = result["story_events"][0]
        episode = turn_controller.get_episode(round_number=7)
        payload_text = json.dumps(episode["events"][0]["payload"])

        self.assertEqual(event["payload"]["host_narration"], "A context-aware host line lands here.")
        self.assertEqual(event["payload"]["host_llm_provider"], "openrouter")
        self.assertEqual(event["payload"]["host_llm_model_id"], "test-host-model")
        self.assertIn("host", event["payload"]["llm_context_digest"])
        self.assertNotIn("host_timeline", payload_text)
        self.assertNotIn("public_timeline", payload_text)
        self.assertNotIn("actor_private_memory", payload_text)
        self.assertNotIn("episode_context", payload_text)

    def test_live_agent_failure_stores_context_digest_without_model_substitution(self) -> None:
        turn_controller.auto_run(6)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            with patch(
                "backend.turn_controller.request_challenge_solution",
                side_effect=RuntimeError("model unavailable"),
            ):
                with patch(
                    "backend.turn_controller.request_host_narration",
                    side_effect=RuntimeError("host unavailable"),
                ):
                    with patch("builtins.print"):
                        result = turn_controller.advance_turn()

        payload = result["story_events"][0]["payload"]
        self.assertEqual(payload["llm_provider"], "openrouter")
        self.assertEqual(
            {attempt["status"] for attempt in payload["attempts"]},
            {"openrouter_failed"},
        )
        conn = database.get_db_connection()
        try:
            attempt_payloads = [
                database.row_to_dict(row)["attempt_payload"]
                for row in conn.execute("SELECT * FROM ChallengeAttempts ORDER BY id").fetchall()
            ]
        finally:
            conn.close()
        self.assertTrue(attempt_payloads)
        self.assertEqual(
            attempt_payloads[0]["llm_context_digest"]["visibility"],
            "contestant_public_plus_own",
        )

    def test_live_agent_receives_generated_scene_context(self) -> None:
        captured: list[dict] = []
        turn_controller.auto_run(9)

        def fake_agent_action(**kwargs):
            captured.append(kwargs)
            return AgentAction(
                dialogue="I am reading the room from the facts I can see.",
                inner_thought="I will decide from my visible context.",
                model_id="test-model",
            )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            with patch("backend.turn_controller.request_agent_action", side_effect=fake_agent_action):
                with patch(
                    "backend.turn_controller.request_host_narration",
                    return_value=HostNarration("A host line.", "test-host-model"),
                ):
                    turn_controller.advance_turn()

        self.assertEqual(captured[0]["step"], "camp_strategy")
        self.assertIn('"step":"camp_strategy"', captured[0]["scene_context"])
        self.assertNotIn("too dangerous to keep", captured[0]["scene_context"])
        self.assertNotIn("four votes is enough", captured[0]["scene_context"])


if __name__ == "__main__":
    unittest.main()
