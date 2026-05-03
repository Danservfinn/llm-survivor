"use client";

import { ApiStateResponse } from '@/types';
import { AgentSprite } from '@/components/common/AgentSprite';

interface PhaseBScrambleProps {
  data: ApiStateResponse;
}

export function PhaseBScramble({ data }: PhaseBScrambleProps) {
  // Get latest whispers (non-public messages)
  const whispers = data.messages
    .filter(m => !m.is_public && m.sender_id !== 'SYSTEM')
    .sort((a, b) => b.id - a.id)
    .slice(0, 15);
  
  // Sort ALL agents alphabetically so they maintain permanent grid spots
  const allAgents = [...data.agents].sort((a, b) => a.pseudonym.localeCompare(b.pseudonym));

  return (
    <div className="h-full relative bg-gbc-bg">
      {/* 4x4 Grid */}
      <div className="grid grid-cols-4 grid-rows-4 gap-4 p-4 h-full relative z-10">
        {allAgents.map((agent, index) => {
          const col = (index % 4) + 1;
          const row = Math.floor(index / 4) + 1;
          
          if (agent.status !== 'active') {
            // Render empty placeholder for eliminated agents
            return <div key={agent.agent_id} style={{ gridColumn: col, gridRow: row }} />;
          }
          
          return (
            <div 
              key={agent.agent_id}
              className="flex flex-col items-center justify-center"
              style={{ gridColumn: col, gridRow: row }}
            >
              {/* HP Bar (Action Points) */}
              <div className="w-12 h-2 bg-gbc-black mb-1 border-[1px] border-gbc-black">
                <div 
                  className="h-full transition-all duration-300"
                  style={{ 
                    width: `${(agent.action_points / 5) * 100}%`,
                    backgroundColor: agent.action_points > 2 ? 'var(--color-gbc-primary)' : 'var(--color-pkmn-red)'
                  }}
                />
              </div>
              <AgentSprite agent={agent} scale={0.8} />
            </div>
          );
        })}
      </div>
      
      {/* Spy Lines Overlay */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none z-0">
        {whispers.map((whisper, index) => {
          const senderIndex = allAgents.findIndex(a => a.pseudonym === whisper.sender_id);
          const receiverIndex = allAgents.findIndex(a => 
            whisper.receiver_ids.includes(a.pseudonym)
          );
          
          if (senderIndex === -1 || receiverIndex === -1) return null;
          
          // Calculate center of grid cells (4x4)
          const x1 = ((senderIndex % 4) * 25) + 12.5;
          const y1 = (Math.floor(senderIndex / 4) * 25) + 12.5;
          const x2 = ((receiverIndex % 4) * 25) + 12.5;
          const y2 = (Math.floor(receiverIndex / 4) * 25) + 12.5;
          
          const receiverName = whisper.receiver_ids[0];
          const isTrusted = (whisper.trust_telemetry[receiverName] || 5) > 5;
          
          return (
            <line
              key={`${whisper.id}-${index}`}
              x1={`${x1}%`}
              y1={`${y1}%`}
              x2={`${x2}%`}
              y2={`${y2}%`}
              stroke={isTrusted ? 'var(--color-gbc-dark)' : 'var(--color-pkmn-red)'}
              strokeWidth="3"
              strokeDasharray={isTrusted ? undefined : '5,5'}
              opacity="0.6"
            />
          );
        })}
      </svg>
      
      {/* Legend */}
      <div className="absolute top-2 right-2 bg-white/90 p-2 border-2 border-gbc-black text-[8px]">
        <div className="flex items-center gap-1 mb-1">
          <div className="w-4 h-1 bg-gbc-dark"></div>
          <span>Trusted (&gt;5)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-4 h-1 bg-pkmn-red border-dashed border-t-2 border-pkmn-red"></div>
          <span>Deception (&lt;=5)</span>
        </div>
      </div>
    </div>
  );
}
