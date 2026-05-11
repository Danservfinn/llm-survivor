import { motion } from "framer-motion";

import { CastTableau } from "@/components/broadcast/CastTableau";
import { LowerThird } from "@/components/broadcast/LowerThird";
import { SpeechBubble } from "@/components/broadcast/SpeechBubble";
import type { Agent, StoryEvent } from "@/types";

interface ConversationSceneProps {
  event: StoryEvent;
  getAgent: (agentId: string) => Agent | undefined;
  agents: Agent[];
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

export function ConversationScene({ event, getAgent, agents }: ConversationSceneProps) {
  const actors = event.actor_ids.map(getAgent).filter(Boolean) as Agent[];
  const primary = actors[0];
  const speakerLines = getSpeakerLines(event);
  const speakerTextByAgent = new Map(speakerLines.map((line) => [line.agent_id, line.text]));
  const speakerIds = speakerLines.map((line) => line.agent_id);
  const isGroupConversation = actors.length > 2;

  return (
    <div className={`conversation-scene ${isGroupConversation ? "is-group-conversation" : ""}`}>
      <div className="camp-background" />
      <div className="scene-bug">{isGroupConversation ? "Group Strategy" : "Camp Strategy"}</div>
      <CastTableau agents={agents} speakerIds={speakerIds} focusIds={event.actor_ids} />
      <div className="conversation-blocking">
        {actors.map((agent, index) => {
          const speakerLine = speakerTextByAgent.get(agent.agent_id);
          const align = !isGroupConversation ? (index === 0 ? "left" : "right") : "center";
          return (
          <motion.div
            key={agent.agent_id}
            className="conversation-actor"
            initial={{ opacity: 0, x: index === 0 ? -28 : 28 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.12 }}
          >
            <div className="speech-slot">
              <SpeechBubble
                speaker={agent}
                text={speakerLine}
                align={align}
              />
            </div>
          </motion.div>
          );
        })}
      </div>
      <div className="scene-note">
        <strong>{event.title}</strong>
        {event.subtitle && <small>{event.subtitle}</small>}
      </div>
      <LowerThird event={event} primaryAgent={primary} />
    </div>
  );
}
