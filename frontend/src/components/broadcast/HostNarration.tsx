import { Portrait } from "@/components/broadcast/Portrait";
import type { Agent, StoryEvent } from "@/types";

interface HostNarrationProps {
  event: StoryEvent;
  host: Agent;
}

export function HostNarration({ event, host }: HostNarrationProps) {
  if (event.kind === "vote_booth") {
    return null;
  }

  const narration = event.payload.host_narration;
  if (typeof narration !== "string" || narration.trim().length === 0) {
    return null;
  }

  return (
    <aside className="host-narration" aria-label="Host narration">
      <Portrait agent={host} size="sm" />
      <div>
        <span>Host Narration</span>
        <p>{narration}</p>
      </div>
    </aside>
  );
}
