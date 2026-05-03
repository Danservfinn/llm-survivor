"use client";

import { Agent } from '@/types';

interface AgentSpriteProps {
  agent: Agent;
  scale?: number;
  isFainting?: boolean;
}

export function AgentSprite({ agent, scale = 1, isFainting = false }: AgentSpriteProps) {
  const imageUrl = `https://api.dicebear.com/9.x/pixel-art/svg?seed=${encodeURIComponent(agent.pseudonym)}`;
  
  const baseSize = 48;
  const size = baseSize * scale;
  
  const isEliminated = agent.status === 'eliminated';
  const hasImmunity = agent.has_immunity;
  
  const imageClasses = [
    'pixelated',
    isEliminated ? 'grayscale opacity-50' : '',
    isFainting ? 'animate-faint' : '',
  ].filter(Boolean).join(' ');
  
  const containerClasses = [
    'inline-flex flex-col items-center justify-center',
    hasImmunity ? 'border-4 border-pkmn-gold animate-pulse rounded' : '',
    'p-1',
  ].filter(Boolean).join(' ');
  
  return (
    <div className={containerClasses}>
      {/* DiceBear SVG sprites are intentionally loaded as raw images. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={imageUrl}
        alt={agent.pseudonym}
        width={size}
        height={size}
        className={imageClasses}
        style={{ imageRendering: 'pixelated' }}
      />
      <span className="mt-1 text-[8px] text-gbc-black text-center leading-tight">
        {agent.pseudonym}
      </span>
    </div>
  );
}
