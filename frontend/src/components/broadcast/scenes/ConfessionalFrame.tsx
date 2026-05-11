import { motion } from "framer-motion";

import { HostNarration } from "@/components/broadcast/HostNarration";
import { LowerThird } from "@/components/broadcast/LowerThird";
import { Portrait } from "@/components/broadcast/Portrait";
import type { Agent, StoryEvent } from "@/types";

interface ConfessionalFrameProps {
  event: StoryEvent;
  getAgent: (agentId: string) => Agent | undefined;
  host: Agent;
}

export function ConfessionalFrame({ event, getAgent, host }: ConfessionalFrameProps) {
  const agent = getAgent(event.actor_ids[0]);

  return (
    <div className="confessional-scene">
      <div className="interview-light" />
      <motion.div
        className="confessional-subject"
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.35 }}
      >
        <Portrait agent={agent} size="lg" isSpeaking={Boolean(event.dialogue)} />
      </motion.div>
      <div className="confessional-copy">
        <span>{event.subtitle ?? "Confessional"}</span>
        <p>{event.dialogue}</p>
        {event.inner_thought && <blockquote>{event.inner_thought}</blockquote>}
      </div>
      <HostNarration event={event} host={host} />
      <LowerThird event={event} primaryAgent={agent} />
    </div>
  );
}
