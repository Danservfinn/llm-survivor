import { motion } from "framer-motion";

import { LowerThird } from "@/components/broadcast/LowerThird";
import { Portrait } from "@/components/broadcast/Portrait";
import { SpeechBubble } from "@/components/broadcast/SpeechBubble";
import type { Agent, StoryEvent } from "@/types";

interface ConversationSceneProps {
  event: StoryEvent;
  getAgent: (agentId: string) => Agent | undefined;
}

interface SpeakerLine {
  agent_id: string;
  text: string;
}

function getSpeakerLines(event: StoryEvent): SpeakerLine[] {
  return Array.isArray(event.payload.speaker_lines)
    ? event.payload.speaker_lines.filter(
        (line): line is SpeakerLine =>
          typeof line === "object" &&
          line !== null &&
          "agent_id" in line &&
          "text" in line &&
          typeof line.agent_id === "string" &&
          typeof line.text === "string",
      )
    : [];
}

export function ConversationScene({ event, getAgent }: ConversationSceneProps) {
  const actors = event.actor_ids.map(getAgent).filter(Boolean) as Agent[];
  const primary = actors[0];
  const speakerLines = getSpeakerLines(event);

  return (
    <div className="conversation-scene">
      <div className="camp-background" />
      <div className="scene-bug">Camp Strategy</div>
      <div className="conversation-blocking">
        {actors.map((agent, index) => (
          <motion.div
            key={agent.agent_id}
            className="conversation-actor"
            initial={{ opacity: 0, x: index === 0 ? -28 : 28 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.12 }}
          >
            <SpeechBubble
              speaker={agent}
              text={speakerLines.find((line) => line.agent_id === agent.agent_id)?.text}
              align={index === 0 ? "left" : "right"}
            />
            <Portrait agent={agent} size="lg" />
          </motion.div>
        ))}
      </div>
      <div className="scene-note">
        <strong>{event.title}</strong>
        {event.subtitle && <small>{event.subtitle}</small>}
      </div>
      <LowerThird event={event} primaryAgent={primary} />
    </div>
  );
}
