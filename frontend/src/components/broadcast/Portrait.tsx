import type { CSSProperties } from "react";

import type { Agent } from "@/types";
import { getAgentVisualProfile } from "@/components/broadcast/avatarProfile";

interface PortraitProps {
  agent?: Agent;
  label?: string;
  size?: "sm" | "md" | "lg";
  muted?: boolean;
  isSpeaking?: boolean;
}

export function Portrait({ agent, label, size = "md", muted = false, isSpeaking = false }: PortraitProps) {
  const name = agent?.pseudonym ?? label ?? "Host";
  const profile = getAgentVisualProfile(agent, name);
  const isImmune = Boolean(agent?.has_immunity);
  const isEliminated = muted || agent?.status === "eliminated";
  const style = {
    "--avatar-primary": profile.primary,
    "--avatar-secondary": profile.secondary,
    "--avatar-accent": profile.accent,
    "--avatar-glow": profile.glow,
    "--avatar-texture": profile.texture,
  } as CSSProperties;

  return (
    <figure
      className={[
        "portrait",
        `portrait-${size}`,
        `avatar-${profile.archetype}`,
        isEliminated ? "muted" : "",
        isImmune ? "is-immune" : "",
        isSpeaking ? "is-speaking" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={style}
      aria-label={`${name} avatar, ${profile.label}`}
    >
      <div className="avatar-shell" aria-hidden="true">
        <div className="avatar-aura" />
        <div className="avatar-body">
          <div className="avatar-grid" />
          <div className="avatar-visor">
            <span />
            <span />
            <span />
          </div>
          <div className="avatar-face">
            <i />
            <i />
          </div>
          <div className="avatar-mouth">
            <b />
            <b />
            <b />
            <b />
          </div>
          <div className="avatar-core" />
          <div className="avatar-signal">
            <span />
            <span />
            <span />
          </div>
        </div>
      </div>
      <figcaption>{name}</figcaption>
      <span className="avatar-role">{profile.roleLabel}</span>
    </figure>
  );
}
