import type { Agent, StoryEvent } from "@/types";
import { getAgentVisualProfile } from "@/components/broadcast/avatarProfile";

interface LowerThirdProps {
  event: StoryEvent;
  primaryAgent?: Agent;
}

export function LowerThird({ event, primaryAgent }: LowerThirdProps) {
  const visualProfile = getAgentVisualProfile(primaryAgent, event.title);
  const provider =
    typeof event.payload.llm_provider === "string"
      ? event.payload.llm_provider
      : typeof event.payload.provider === "string"
        ? event.payload.provider
        : null;
  const status =
    provider ??
    (typeof event.payload.status === "string" ? event.payload.status : null) ??
    (primaryAgent?.has_immunity ? "immune" : null);

  return (
    <div className="lower-third">
      <div>
        <span>{event.scene.toUpperCase()} | {event.shot.replaceAll("_", " ").toUpperCase()}</span>
        <strong>{primaryAgent?.pseudonym ?? event.title}</strong>
      </div>
      <p>{primaryAgent ? visualProfile.roleLabel : event.kind.replaceAll("_", " ")}</p>
      {status && <em>{status.replaceAll("_", " ")}</em>}
    </div>
  );
}
