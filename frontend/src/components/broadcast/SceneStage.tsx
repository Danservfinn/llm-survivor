"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Clapperboard } from "lucide-react";

import { ConfessionalFrame } from "@/components/broadcast/scenes/ConfessionalFrame";
import { ConversationScene } from "@/components/broadcast/scenes/ConversationScene";
import { TribalCouncilScene } from "@/components/broadcast/scenes/TribalCouncilScene";
import { VoteRevealScene } from "@/components/broadcast/scenes/VoteRevealScene";
import type { Agent, StoryEvent } from "@/types";

export const HOST_AGENT: Agent = {
  agent_id: "host",
  pseudonym: "Host",
  archetype: "island host",
  team_id: "Production",
  status: "active",
  has_immunity: 0,
  confessional_memory: "",
  action_points: 0,
  portrait_seed: "llm-survivor-host",
};

interface SceneStageProps {
  event: StoryEvent | null;
  agents: Agent[];
  reducedMotion: boolean;
}

export function SceneStage({ event, agents, reducedMotion }: SceneStageProps) {
  const getAgent = (agentId: string) =>
    agentId === HOST_AGENT.agent_id ? HOST_AGENT : agents.find((agent) => agent.agent_id === agentId);

  if (!event) {
    return (
      <div className="scene-stage empty-stage">
        <Clapperboard size={42} />
        <h2>Round replay is waiting for turns.</h2>
        <p>Use Next Turn or Build Round to generate the edited episode beats.</p>
      </div>
    );
  }

  return (
    <div className={`scene-stage scene-${event.scene}`}>
      <AnimatePresence initial={false} mode="sync">
        <motion.div
          key={event.id}
          className="scene-motion"
          initial={reducedMotion ? { opacity: 0 } : { opacity: 0, scale: 1.01, y: 4 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reducedMotion ? 0.05 : 0.18, ease: "easeOut" }}
        >
          {event.kind === "conversation" && <ConversationScene event={event} getAgent={getAgent} />}
          {(event.kind === "confessional" || event.kind === "exit_confessional") && (
            <ConfessionalFrame event={event} getAgent={getAgent} host={HOST_AGENT} />
          )}
          {event.kind === "vote_reveal" && <VoteRevealScene event={event} getAgent={getAgent} host={HOST_AGENT} />}
          {event.kind !== "conversation" &&
            event.kind !== "confessional" &&
            event.kind !== "exit_confessional" &&
            event.kind !== "vote_reveal" && <TribalCouncilScene event={event} getAgent={getAgent} host={HOST_AGENT} />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
