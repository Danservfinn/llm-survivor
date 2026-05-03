import type { Agent, StoryEvent } from "@/types";

interface LowerThirdProps {
  event: StoryEvent;
  primaryAgent?: Agent;
}

export function LowerThird({ event, primaryAgent }: LowerThirdProps) {
  return (
    <div className="lower-third">
      <div>
        <span>{event.scene.toUpperCase()} | {event.shot.replaceAll("_", " ").toUpperCase()}</span>
        <strong>{primaryAgent?.pseudonym ?? event.title}</strong>
      </div>
      <p>{primaryAgent?.archetype ?? event.kind.replaceAll("_", " ")}</p>
    </div>
  );
}
