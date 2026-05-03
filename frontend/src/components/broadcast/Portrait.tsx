import type { Agent } from "@/types";

interface PortraitProps {
  agent?: Agent;
  label?: string;
  size?: "sm" | "md" | "lg";
  muted?: boolean;
}

export function Portrait({ agent, label, size = "md", muted = false }: PortraitProps) {
  const seed = encodeURIComponent(agent?.portrait_seed || agent?.agent_id || label || "host");
  const name = agent?.pseudonym ?? label ?? "Host";
  const src = agent
    ? `https://api.dicebear.com/8.x/bottts-neutral/svg?seed=${seed}&backgroundColor=b6e3f4,c0aede,ffd5dc,d1d4f9`
    : `https://api.dicebear.com/8.x/shapes/svg?seed=${seed}&backgroundColor=1f2937`;

  return (
    <figure className={`portrait portrait-${size} ${muted ? "muted" : ""}`}>
      {/* DiceBear SVGs render directly without Next image optimization. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={`${name} avatar`} />
      <figcaption>{name}</figcaption>
    </figure>
  );
}
