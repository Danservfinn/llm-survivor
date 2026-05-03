import { motion } from "framer-motion";

import { Portrait } from "@/components/broadcast/Portrait";
import { SpeechBubble } from "@/components/broadcast/SpeechBubble";
import type { Agent, StoryEvent } from "@/types";

interface VoteRevealSceneProps {
  event: StoryEvent;
  getAgent: (agentId: string) => Agent | undefined;
  host: Agent;
}

export function VoteRevealScene({ event, getAgent, host }: VoteRevealSceneProps) {
  const target = getAgent(event.target_ids[0]);
  const tally = event.payload.revealed_tally as Record<string, number> | undefined;

  return (
    <div className="vote-reveal-scene">
      <div className="scene-bug">Vote Reveal</div>
      <div className="vote-host">
        <SpeechBubble speaker={host} text={`${event.title}: ${target?.pseudonym ?? event.dialogue}.`} />
        <Portrait agent={host} size="md" />
      </div>
      <motion.div
        className="vote-card"
        initial={{ rotateY: 90, opacity: 0 }}
        animate={{ rotateY: 0, opacity: 1 }}
        transition={{ duration: 0.55, ease: "easeOut" }}
      >
        <span>{event.title}</span>
        <strong>{target?.pseudonym ?? event.dialogue}</strong>
      </motion.div>
      <div className="vote-tally">
        <strong>Public Tally</strong>
        {tally && Object.keys(tally).length > 0 ? (
          Object.entries(tally).map(([agentId, count]) => (
            <div key={agentId}>
              <span>{getAgent(agentId)?.pseudonym ?? agentId}</span>
              <b>{count}</b>
            </div>
          ))
        ) : (
          <p>No votes revealed.</p>
        )}
      </div>
    </div>
  );
}
