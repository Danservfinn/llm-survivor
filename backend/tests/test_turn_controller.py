from __future__ import annotations

import json
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from backend import database
from backend import model_rosters
from backend import turn_controller
from backend.openrouter_client import AgentAction, HostNarration


class TurnControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": "", "LLM_PROVIDER": "openrouter"},
            clear=False,
        )
        self.env_patch.start()
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DATABASE_PATH = Path(self.temp_dir.name) / "survivor.db"
        database.seed_demo(reset=True)

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_advance_turn_creates_one_turn_and_ordered_story_events(self) -> None:
        result = turn_controller.advance_turn()

        self.assertIsNotNone(result["turn"])
        self.assertEqual(result["turn"]["turn_index"], 1)
        self.assertGreaterEqual(len(result["story_events"]), 1)

        state = turn_controller.get_state()
        self.assertEqual(state["turn_count"], 1)
        self.assertEqual(state["story_event_count"], len(result["story_events"]))
        self.assertEqual(
            [event["sequence"] for event in result["story_events"]],
            list(range(len(result["story_events"]))),
        )

    def test_tribal_fixture_generates_expected_sequence_without_elimination_spoiler(self) -> None:
        result = turn_controller.auto_run(40)
        events = result["story_events"]
        kinds = [event["kind"] for event in events]

        self.assertIn("challenge_intro", kinds)
        self.assertIn("challenge_attempts", kinds)
        self.assertIn("challenge_result", kinds)
        self.assertIn("conversation", kinds)
        self.assertIn("confessional", kinds)
        self.assertIn("host_question", kinds)
        self.assertEqual(kinds.count("vote_booth"), 6)
        self.assertEqual(kinds.count("vote_reveal"), 6)
        self.assertIn("elimination", kinds)
        self.assertIn("exit_confessional", kinds)

        elimination_index = kinds.index("elimination")
        before_elimination = json.dumps(events[:elimination_index])
        self.assertNotIn("eliminated_id", before_elimination)
        self.assertNotIn("your run ends here", before_elimination.lower())

    def test_all_camp_strategy_scenes_precede_tribal_conference(self) -> None:
        result = turn_controller.auto_run(40)
        events = result["story_events"]
        first_tribal_index = next(index for index, event in enumerate(events) if event["scene"] == "tribal")
        camp_after_tribal = [
            event
            for event in events[first_tribal_index + 1 :]
            if event["scene"] in {"camp", "confessional"} and event["kind"] in {"conversation", "confessional"}
        ]

        pre_tribal_kinds = [event["kind"] for event in events[:first_tribal_index]]
        canonical_order = [
            "challenge_intro",
            "challenge_attempts",
            "challenge_result",
            "challenge_solver_spotlight",
            "confessional",
            "confessional",
        ]
        cursor = 0
        for expected_kind in canonical_order:
            cursor = pre_tribal_kinds.index(expected_kind, cursor) + 1
        group_discussions = [
            event
            for event in events[:first_tribal_index]
            if event["payload"].get("conversation_type") in {"group_discussion", "alliance"}
        ]
        self.assertEqual(len(group_discussions), 5)
        self.assertEqual(events[first_tribal_index]["kind"], "establishing")
        self.assertEqual(camp_after_tribal, [])

    def test_host_calls_for_vote_before_vote_booth_sequence(self) -> None:
        result = turn_controller.auto_run(40)
        events = result["story_events"]
        vote_call_index = next(index for index, event in enumerate(events) if event["kind"] == "vote_call")
        first_vote_index = next(index for index, event in enumerate(events) if event["kind"] == "vote_booth")
        vote_call = events[vote_call_index]

        self.assertLess(vote_call_index, first_vote_index)
        self.assertEqual(vote_call["actor_ids"], ["host"])
        self.assertEqual(vote_call["scene"], "tribal")
        self.assertIn("time to vote", vote_call["dialogue"].lower())

    def test_agent_visible_text_stays_first_person(self) -> None:
        result = turn_controller.auto_run(40)
        events = result["story_events"]
        agent_names = {agent["agent_id"]: agent["pseudonym"] for agent in result["state"]["agents"]}
        agent_authored = [
            event
            for event in events
            if event["kind"] in {"conversation", "confessional", "tribal_answer", "exit_confessional", "finale_pitch"}
        ]

        for event in agent_authored:
            text = " ".join(
                value
                for value in [event.get("dialogue"), event.get("inner_thought")]
                if isinstance(value, str)
            )
            actor_id = next((candidate for candidate in event["actor_ids"] if candidate != "host"), None)
            name = agent_names.get(actor_id or "")
            if not name:
                continue
            self.assertNotIn(f"{name} is ", text)
            self.assertNotIn(f"{name} leaves ", text)
            self.assertNotIn(f"{name} thinks ", text)
            self.assertNotIn(f"{name} wants ", text)

    def test_each_agent_speaks_twice_across_camp_challenge_strategy(self) -> None:
        result = turn_controller.auto_run(40)
        events = result["story_events"]
        first_tribal_index = next(index for index, event in enumerate(events) if event["scene"] == "tribal")
        pre_tribal = events[:first_tribal_index]
        challenge_intro_index = next(index for index, event in enumerate(pre_tribal) if event["kind"] == "challenge_intro")
        speaking_counts: Counter[str] = Counter()

        self.assertGreaterEqual(
            len([event for event in pre_tribal[:challenge_intro_index] if event["scene"] in {"camp", "confessional"}]),
            5,
        )
        for event in pre_tribal:
            if event["scene"] not in {"camp", "confessional"}:
                continue
            speaker_id = next((agent_id for agent_id in event["actor_ids"] if agent_id != "host"), None)
            if speaker_id:
                speaking_counts[speaker_id] += 1

        active_ids = {agent["agent_id"] for agent in result["state"]["agents"] if agent["status"] == "active"}
        for agent_id in active_ids:
            self.assertGreaterEqual(speaking_counts[agent_id], 2, agent_id)

    def test_generated_conversation_scenes_include_line_for_each_visible_agent(self) -> None:
        result = turn_controller.auto_run(40)
        events = result["story_events"]
        multi_agent_conversations = [
            event
            for event in events
            if event["kind"] == "conversation"
            and len([actor_id for actor_id in event["actor_ids"] if actor_id != "host"]) > 1
        ]

        self.assertGreater(len(multi_agent_conversations), 0)
        for event in multi_agent_conversations:
            contestant_ids = [actor_id for actor_id in event["actor_ids"] if actor_id != "host"]
            speaker_lines = event["payload"].get("speaker_lines")
            self.assertIsInstance(speaker_lines, list, event["title"])
            line_ids = {
                line.get("agent_id")
                for line in speaker_lines
                if isinstance(line, dict) and isinstance(line.get("text"), str) and line.get("text", "").strip()
            }

            self.assertTrue(set(contestant_ids).issubset(line_ids), event["title"])

    def test_pre_challenge_dialogue_does_not_reference_completed_challenge_result(self) -> None:
        result = turn_controller.auto_run(40)
        events = result["story_events"]
        challenge_intro_index = next(index for index, event in enumerate(events) if event["kind"] == "challenge_intro")
        pre_challenge_events = events[:challenge_intro_index]
        forbidden_phrases = [
            "challenge result changed",
            "result changed the vote",
            "now that immunity",
        ]

        for event in pre_challenge_events:
            if event["kind"] not in {"conversation", "confessional"}:
                continue
            line_text = " ".join(
                line.get("text", "")
                for line in event["payload"].get("speaker_lines", [])
                if isinstance(line, dict)
            )
            text = " ".join(
                value
                for value in [event.get("dialogue"), event.get("inner_thought"), line_text]
                if isinstance(value, str)
            ).lower()
            for phrase in forbidden_phrases:
                self.assertNotIn(phrase, text, event["title"])

    def test_vote_booth_shows_target_and_explanation(self) -> None:
        turn_controller.auto_run(40)
        events = turn_controller.list_story_events(round_number=7)
        vote_events = [event for event in events if event["kind"] == "vote_booth"]

        self.assertEqual(len(vote_events), 6)
        for event in vote_events:
            self.assertEqual(len(event["target_ids"]), 1)
            self.assertIn("vote_target_id", event["payload"])
            self.assertIn("vote_target_name", event["payload"])
            self.assertIn("vote_explanation", event["payload"])
            self.assertIn("ui_vote_analysis", event["payload"])
            self.assertEqual(
                event["payload"]["ui_vote_analysis"]["label"],
                "UI analysis, not model-authored text",
            )
            self.assertIn(event["payload"]["vote_target_name"], event["dialogue"])
            self.assertGreater(len(event["payload"]["vote_explanation"]), 20)

    def test_vote_reveal_keeps_elimination_payload_until_elimination_event(self) -> None:
        turn_controller.auto_run(40)
        events = turn_controller.list_story_events(round_number=7)
        reveal_events = [event for event in events if event["kind"] == "vote_reveal"]

        self.assertEqual(len(reveal_events), 6)
        for event in reveal_events:
            self.assertNotIn("eliminated_id", event["payload"])
            self.assertNotEqual(event["kind"], "elimination")

        elimination = next(event for event in events if event["kind"] == "elimination")
        self.assertIn(elimination["payload"]["eliminated_id"], {agent["agent_id"] for agent in turn_controller.get_state()["agents"]})

    def test_individual_challenge_awards_immunity_to_first_valid_solver(self) -> None:
        result = turn_controller.auto_run(8)
        events = result["story_events"]
        attempts_event = next(event for event in events if event["kind"] == "challenge_attempts")
        result_event = next(event for event in events if event["kind"] == "challenge_result")

        self.assertEqual(attempts_event["actor_ids"], ["host"])
        self.assertEqual(len(attempts_event["target_ids"]), 6)
        self.assertEqual(result_event["actor_ids"], ["host"])
        self.assertEqual(result_event["payload"]["winning_agent_id"], "agent-alpha")
        self.assertEqual(result_event["payload"]["immunity_agent_ids"], ["agent-alpha"])
        state = result["state"]
        immune_agents = [agent["agent_id"] for agent in state["agents"] if agent["has_immunity"]]
        self.assertEqual(immune_agents, ["agent-alpha"])

    def test_all_free_roster_seeds_only_free_openrouter_models(self) -> None:
        rosters = model_rosters.list_model_rosters()
        free_roster = next(roster for roster in rosters if roster["id"] == "all_free_openrouter")
        self.assertEqual(free_roster["name"], "All Free OpenRouter Models")
        self.assertTrue(free_roster["models"])
        self.assertTrue(all(model["status"] == "free_test" for model in free_roster["models"]))

        database.seed_demo(reset=True, roster_preset="all_free_openrouter")
        state = turn_controller.get_state()
        active_agents = [agent for agent in state["agents"] if agent["status"] == "active"]

        self.assertEqual(len(active_agents), len(free_roster["models"]))
        self.assertGreaterEqual(len(active_agents), 3)
        self.assertEqual(
            [agent["model_id"] for agent in active_agents],
            [model["model_id"] for model in free_roster["models"]],
        )

    def test_all_free_roster_replay_does_not_leak_default_model_names(self) -> None:
        database.seed_demo(reset=True, roster_preset="all_free_openrouter")
        result = turn_controller.auto_run(40)
        full_text = json.dumps(result["story_events"])

        for old_name in [
            "GPT-4.1",
            "Claude Sonnet 4.5",
            "Gemini 2.5 Pro",
            "Grok 4.3",
            "Llama 3.3 70B",
            "Mistral Large",
        ]:
            self.assertNotIn(old_name, full_text)
        self.assertIn("Owl Alpha", full_text)
        self.assertIn("Nemotron 3 Super 120B Free", full_text)

    def test_local_ollama_roster_seeds_only_local_models(self) -> None:
        rosters = model_rosters.list_model_rosters()
        local_roster = next(roster for roster in rosters if roster["id"] == "local_ollama")
        self.assertEqual(local_roster["name"], "All Local Ollama Models")
        self.assertEqual(len(local_roster["models"]), 6)
        self.assertTrue(all(model["status"] == "local_ollama" for model in local_roster["models"]))

        database.seed_demo(reset=True, roster_preset="local_ollama")
        state = turn_controller.get_state()
        active_agents = [agent for agent in state["agents"] if agent["status"] == "active"]

        self.assertEqual(
            [agent["model_id"] for agent in active_agents],
            [model["model_id"] for model in local_roster["models"]],
        )
        self.assertIn("Qwen 2.5 1.5B Local", json.dumps(state["agents"]))
        self.assertNotIn("local contender", json.dumps(state["agents"]).lower())

    def test_group_discussions_create_social_summary_and_alliance_records(self) -> None:
        result = turn_controller.advance_turn()
        group_events = [
            event
            for event in result["story_events"]
            if event["payload"].get("conversation_type") in {"group_discussion", "alliance"}
        ]
        state = turn_controller.get_state()
        social = state["social"]

        self.assertEqual(len(group_events), 2)
        self.assertGreaterEqual(len(social["group_discussions"]), 2)
        self.assertGreaterEqual(len(social["alliances"]), 1)
        for event in group_events:
            participant_ids = event["payload"]["participant_ids"]
            self.assertGreaterEqual(len(participant_ids), 2)
            self.assertLessEqual(len(participant_ids), 5)
            self.assertEqual(event["payload"]["privacy"], "participants_only")
            self.assertEqual(
                {line["agent_id"] for line in event["payload"]["speaker_lines"]},
                set(participant_ids),
            )

    def test_challenge_solver_spotlight_explains_first_solver(self) -> None:
        result = turn_controller.auto_run(9)
        spotlight = next(event for event in result["story_events"] if event["kind"] == "challenge_solver_spotlight")

        self.assertEqual(spotlight["actor_ids"], ["host", "agent-alpha"])
        self.assertEqual(spotlight["payload"]["winning_agent_id"], "agent-alpha")
        self.assertEqual(spotlight["payload"]["response_ms"], 5000)
        self.assertIn("5.00 seconds", spotlight["dialogue"])
        self.assertIn("Connected matching color endpoints", spotlight["payload"]["solver_explanation"])

    def test_auto_run_to_end_declares_winner_from_jury_vote(self) -> None:
        result = turn_controller.auto_run_to_end(
            max_rounds=8,
            max_turns=260,
            max_live_calls=0,
            max_estimated_cost_cents=0,
        )

        self.assertIsNotNone(result["state"]["game"]["winner"])
        self.assertEqual(result["state"]["game"]["phase"], "completed")
        self.assertTrue(result["summary"]["finale_status"]["winner_declared"])
        final_events = turn_controller.list_story_events(round_number=result["state"]["game"]["current_round"])
        winner_event = next(event for event in final_events if event["kind"] == "winner_declared")
        self.assertEqual(winner_event["actor_ids"], ["host"])
        self.assertEqual(winner_event["target_ids"], [result["state"]["game"]["winner"]])

    def test_broadcast_identity_and_narration_are_present(self) -> None:
        result = turn_controller.auto_run(40)
        events = result["story_events"]
        state = result["state"]
        agent_names = {agent["pseudonym"] for agent in state["agents"]}

        self.assertIn("Grok 4.3", agent_names)
        self.assertIn("Claude Sonnet 4.5", agent_names)
        broadcast_text = json.dumps(
            [
                {
                    "title": event["title"],
                    "dialogue": event["dialogue"],
                    "subtitle": event["subtitle"],
                    "inner_thought": event["inner_thought"],
                }
                for event in events
            ]
        )
        self.assertNotIn("x-ai/grok-4.3", broadcast_text)

        for event in events:
            narration = event["payload"].get("host_narration")
            if event["kind"] == "vote_booth":
                self.assertIsNone(narration)
                self.assertIn("vote_explanation", event["payload"])
            else:
                self.assertIsInstance(narration, str)
                self.assertGreater(len(narration), 20)

    def test_replaying_story_events_does_not_mutate_state(self) -> None:
        turn_controller.auto_run(12)
        before = turn_controller.get_state()
        first_read = turn_controller.list_story_events(round_number=7)
        second_read = turn_controller.list_story_events(round_number=7)
        after = turn_controller.get_state()

        self.assertEqual(first_read, second_read)
        self.assertEqual(before["turn_count"], after["turn_count"])
        self.assertEqual(before["story_event_count"], after["story_event_count"])

    def test_auto_run_is_bounded(self) -> None:
        result = turn_controller.auto_run(3)

        self.assertEqual(len(result["turns"]), 3)
        self.assertEqual(result["state"]["game"]["turn_index"], 3)

    def test_start_next_round_resets_turns_and_replay_for_remaining_agents(self) -> None:
        turn_controller.auto_run(40)

        result = turn_controller.start_next_round()

        self.assertTrue(result["round_started"])
        self.assertEqual(result["state"]["game"]["current_round"], 8)
        self.assertEqual(result["state"]["game"]["phase"], "round")
        self.assertEqual(result["state"]["game"]["phase_step"], "camp_pre_challenge_read")
        self.assertEqual(result["state"]["game"]["turn_index"], 0)
        self.assertEqual(result["state"]["viewer_state"]["round"], 8)
        self.assertEqual(result["state"]["viewer_state"]["replay_index"], 0)
        self.assertFalse(result["state"]["viewer_state"]["is_playing"])

    def test_next_round_uses_remaining_active_voters(self) -> None:
        turn_controller.auto_run(40)
        turn_controller.start_next_round()

        result = turn_controller.auto_run(40)
        kinds = [event["kind"] for event in result["story_events"]]

        self.assertEqual(kinds.count("vote_booth"), 5)
        self.assertEqual(kinds.count("vote_reveal"), 5)
        self.assertEqual(result["state"]["game"]["phase_step"], "complete")

    def test_openrouter_without_key_uses_deterministic_fallback(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": ""}, clear=False):
            result = turn_controller.advance_turn()

            self.assertEqual(result["state"]["llm"]["provider"], "openrouter")
            self.assertFalse(result["state"]["llm"]["openrouter_configured"])
            self.assertEqual(result["story_events"][0]["payload"]["llm_provider"], "deterministic")

    def test_live_agent_action_metadata_is_stored_in_payload(self) -> None:
        action = AgentAction(
            dialogue="I need to keep the swing vote close without promising more than I can pay back.",
            inner_thought="I am protecting my middle position while leaving myself an exit.",
            model_id="test/model",
            move_type="reassure_ally",
            intended_effect="Keep the swing vote available after the challenge.",
            confidence=0.64,
            strategic_summary="I am protecting my middle position while leaving myself an exit.",
            win_condition="I improve my win path by keeping the swing vote dependent on me.",
            threat_assessment="I see a rushed majority as the threat because it removes my options.",
            leverage_plan="I use conditional reassurance so the swing vote still needs my number.",
            risk_control="I avoid overpromising so I can pivot if the challenge changes the board.",
            jury_positioning="I want this move to look controlled instead of passive.",
            strategic_score=0.94,
            prompt_profile="win-max-v2-strategy-contract",
        )
        narration = HostNarration(
            host_narration="A live model turns the opening camp read into a positioning move.",
            model_id="host/model",
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            with patch("backend.turn_controller.request_agent_action", return_value=action):
                with patch("backend.turn_controller.request_host_narration", return_value=narration):
                    result = turn_controller.advance_turn()

        event = result["story_events"][0]
        payload = event["payload"]
        self.assertEqual(payload["llm_provider"], "openrouter")
        self.assertEqual(payload["llm_model_id"], "test/model")
        self.assertEqual(payload["strategic_summary"], action.strategic_summary)
        self.assertEqual(payload["move_type"], "reassure_ally")
        self.assertEqual(payload["intended_effect"], "Keep the swing vote available after the challenge.")
        self.assertEqual(payload["confidence"], 0.64)
        self.assertEqual(payload["win_condition"], "I improve my win path by keeping the swing vote dependent on me.")
        self.assertEqual(payload["strategic_score"], 0.94)
        self.assertEqual(payload["prompt_profile"], "win-max-v2-strategy-contract")
        self.assertEqual(event["inner_thought"], action.inner_thought)

    def test_live_conversation_second_agent_receives_first_line_as_context(self) -> None:
        captured: list[dict] = []

        def fake_agent_action(**kwargs):
            captured.append(kwargs)
            if len(captured) == 1:
                return AgentAction(
                    dialogue="I need to know whether you are with me before immunity changes the board.",
                    inner_thought="I am testing the first commitment.",
                    model_id="primary/model",
                    move_type="test_loyalty",
                    intended_effect="Force the other speaker to answer the commitment.",
                    confidence=0.71,
                    strategic_summary="I am testing whether this promise is real.",
                )
            return AgentAction(
                dialogue="I am with you if the vote still protects my path after the challenge.",
                inner_thought="I am answering while keeping a conditional exit.",
                model_id="reply/model",
                move_type="reassure_ally",
                intended_effect="Answer the first speaker without locking every option.",
                confidence=0.66,
                strategic_summary="I am replying directly but preserving leverage.",
            )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}, clear=False):
            with patch("backend.turn_controller.request_agent_action", side_effect=fake_agent_action):
                with patch(
                    "backend.turn_controller.request_host_narration",
                    return_value=HostNarration("A host line.", "host/model"),
                ):
                    result = turn_controller.advance_turn()

        self.assertGreaterEqual(len(captured), 2)
        first_actor_id = captured[0]["actor"]["agent_id"]
        reply_actor_id = captured[1]["actor"]["agent_id"]
        self.assertNotEqual(first_actor_id, reply_actor_id)
        self.assertIn("Immediate conversation to answer", captured[1]["scene_context"])
        self.assertIn("I need to know whether you are with me", captured[1]["scene_context"])

        event = result["story_events"][0]
        speaker_lines = event["payload"]["speaker_lines"]
        self.assertEqual(speaker_lines[0]["text"], "I need to know whether you are with me before immunity changes the board.")
        self.assertEqual(speaker_lines[1]["text"], "I am with you if the vote still protects my path after the challenge.")
        reply_metadata = event["payload"]["speaker_line_metadata"][1]
        self.assertEqual(reply_metadata["llm_provider"], "openrouter")
        self.assertEqual(reply_metadata["responds_to_agent_id"], first_actor_id)


if __name__ == "__main__":
    unittest.main()
