import { Portrait } from "@/components/broadcast/Portrait";
import type { Agent } from "@/types";

interface CastTableauProps {
  agents: Agent[];
  speakerIds?: string[];
  focusIds?: string[];
}

export function CastTableau({ agents, speakerIds = [], focusIds = [] }: CastTableauProps) {
  const visibleAgents = agents
    .filter((agent) => agent.status !== "eliminated")
    .slice(0, 6);
  const cast = visibleAgents.length > 0 ? visibleAgents : agents.slice(0, 6);

  return (
    <div className={`conference-tableau cast-count-${cast.length}`} aria-label="Active model cast">
      {cast.map((agent, index) => {
        const isSpeaking = speakerIds.includes(agent.agent_id);
        const isFocused = focusIds.includes(agent.agent_id) || isSpeaking;
        return (
          <div
            key={agent.agent_id}
            className={[
              "cast-agent",
              `cast-slot-${index}`,
              isFocused ? "is-focused" : "",
              isSpeaking ? "is-speaking" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <Portrait agent={agent} size="lg" isSpeaking={isSpeaking} muted={!isFocused && speakerIds.length > 0} />
            <div className="cast-performance-dots" aria-hidden="true">
              <span />
              <span />
              <span />
              <span />
              <span />
            </div>
          </div>
        );
      })}
    </div>
  );
}
