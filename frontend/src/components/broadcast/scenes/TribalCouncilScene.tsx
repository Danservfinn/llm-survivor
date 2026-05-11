import { motion } from "framer-motion";

import { CastTableau } from "@/components/broadcast/CastTableau";
import { LowerThird } from "@/components/broadcast/LowerThird";
import { Portrait } from "@/components/broadcast/Portrait";
import { SpeechBubble } from "@/components/broadcast/SpeechBubble";
import type { Agent, StoryEvent } from "@/types";

interface TribalCouncilSceneProps {
  event: StoryEvent;
  getAgent: (agentId: string) => Agent | undefined;
  host: Agent;
  agents: Agent[];
}

export function TribalCouncilScene({ event, getAgent, host, agents }: TribalCouncilSceneProps) {
  const primaryAgent = getAgent(event.actor_ids.find((id) => id !== "host") ?? "");
  const lowerThirdAgent = primaryAgent ?? (event.actor_ids.includes("host") ? host : undefined);
  const isElimination = event.kind === "elimination";
  const isVoteBooth = event.kind === "vote_booth";
  const speaker = primaryAgent ?? (event.actor_ids.includes("host") || event.kind === "establishing" ? host : undefined);
  const voteTargetName =
    typeof event.payload.vote_target_name === "string"
      ? event.payload.vote_target_name
      : getAgent(event.target_ids[0] ?? "")?.pseudonym;
  const voteExplanation =
    typeof event.payload.vote_explanation === "string" && event.payload.vote_explanation.trim()
      ? event.payload.vote_explanation
      : null;
  const spokenLine = isVoteBooth && voteExplanation && !event.dialogue.includes(voteExplanation)
    ? `I am voting for ${voteTargetName}. ${voteExplanation}`
    : event.dialogue;
  const sceneDetail = isVoteBooth ? spokenLine : event.subtitle;
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
      {!isVoteBooth && <CastTableau agents={agents} speakerIds={speaker ? [speaker.agent_id] : []} focusIds={event.actor_ids} />}
      <div className="tribal-blocking">
        {isVoteBooth ? (
          <motion.div className="voting-booth" initial={{ y: 24, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
            <div className="speech-slot">
              <SpeechBubble speaker={speaker} text={spokenLine} align="center" />
            </div>
            <div className="portrait-slot">
              <Portrait agent={primaryAgent} size="lg" isSpeaking={Boolean(spokenLine)} />
            </div>
            <div className="vote-intent-card">
              <span>Vote</span>
              <strong>{voteTargetName}</strong>
            </div>
          </motion.div>
        ) : (
          <>
            <div className="tribal-speaker">
              <div className="speech-slot">
                {!primaryAgent && <SpeechBubble speaker={speaker} text={spokenLine} align="center" />}
              </div>
              <div className="portrait-slot">
                <Portrait agent={host} size="md" isSpeaking={!primaryAgent && Boolean(spokenLine)} />
              </div>
            </div>
            {primaryAgent && (
              <div className="tribal-speaker">
                <div className="speech-slot">
                  <SpeechBubble speaker={speaker} text={spokenLine} align="center" />
                </div>
                <div className="portrait-slot">
                  <Portrait agent={primaryAgent} size="lg" muted={isElimination} isSpeaking={Boolean(spokenLine)} />
                </div>
              </div>
            )}
          </>
        )}
      </div>
      <div className="scene-note">
        <strong>{event.title}</strong>
        {sceneDetail && <small>{sceneDetail}</small>}
      </div>
      <LowerThird event={event} primaryAgent={lowerThirdAgent} />
    </div>
  );
}
