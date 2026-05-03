import { motion } from "framer-motion";

import { LowerThird } from "@/components/broadcast/LowerThird";
import { Portrait } from "@/components/broadcast/Portrait";
import { SpeechBubble } from "@/components/broadcast/SpeechBubble";
import type { Agent, StoryEvent } from "@/types";

interface TribalCouncilSceneProps {
  event: StoryEvent;
  getAgent: (agentId: string) => Agent | undefined;
  host: Agent;
}

export function TribalCouncilScene({ event, getAgent, host }: TribalCouncilSceneProps) {
  const primaryAgent = getAgent(event.actor_ids.find((id) => id !== "host") ?? "");
  const lowerThirdAgent = primaryAgent ?? (event.actor_ids.includes("host") ? host : undefined);
  const isElimination = event.kind === "elimination";
  const isVoteBooth = event.kind === "vote_booth";
  const speaker = primaryAgent ?? (event.actor_ids.includes("host") || event.kind === "establishing" ? host : undefined);
  const voteTargetName =
    typeof event.payload.vote_target_name === "string"
      ? event.payload.vote_target_name
      : getAgent(event.target_ids[0] ?? "")?.pseudonym;
  const spokenLine = event.dialogue;
  const sceneLabel =
    event.scene === "challenge"
      ? "Challenge"
      : event.scene === "finale"
        ? "Finale"
        : event.scene === "memory"
          ? "Season Ledger"
          : "Tribal Conference";

  return (
    <div className={`tribal-scene scene-${event.scene} ${isElimination ? "is-elimination" : ""} ${isVoteBooth ? "is-vote-booth" : ""}`}>
      <div className="fireline" />
      <div className="scene-bug">{sceneLabel}</div>
      <div className="tribal-blocking">
        {isVoteBooth ? (
          <motion.div className="voting-booth" initial={{ y: 24, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
            <SpeechBubble speaker={speaker} text={spokenLine} align="center" />
            <Portrait agent={primaryAgent} size="lg" />
            <div className="vote-intent-card">
              <span>Vote</span>
              <strong>{voteTargetName}</strong>
            </div>
          </motion.div>
        ) : (
          <>
            <div className="tribal-speaker">
              {!primaryAgent && <SpeechBubble speaker={speaker} text={spokenLine} align="center" />}
              <Portrait agent={host} size="md" />
            </div>
            {primaryAgent && (
              <div className="tribal-speaker">
                <SpeechBubble speaker={speaker} text={spokenLine} align="center" />
                <Portrait agent={primaryAgent} size="lg" muted={isElimination} />
              </div>
            )}
          </>
        )}
      </div>
      <div className="scene-note">
        <strong>{event.title}</strong>
        {event.subtitle && <small>{event.subtitle}</small>}
      </div>
      <LowerThird event={event} primaryAgent={lowerThirdAgent} />
    </div>
  );
}
