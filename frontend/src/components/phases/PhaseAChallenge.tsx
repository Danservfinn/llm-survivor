"use client";

import { ApiStateResponse } from '@/types';
import { AgentSprite } from '@/components/common/AgentSprite';
import { DialogBox } from '@/components/common/DialogBox';

interface PhaseAChallengeProps {
  data: ApiStateResponse;
}

export function PhaseAChallenge({ data }: PhaseAChallengeProps) {
  const activeAgents = data.agents.filter(a => a.status === 'active');
  
  // Group by team
  const teamAlpha = activeAgents.filter(a => a.team_id === 'Team_Alpha');
  const teamBeta = activeAgents.filter(a => a.team_id === 'Team_Beta');
  
  // Get latest public message
  const latestPublicMessage = data.messages
    .filter(m => m.is_public)
    .sort((a, b) => b.id - a.id)[0];
  
  const dialogText = latestPublicMessage 
    ? `${latestPublicMessage.sender_id} used PUBLIC CHAT! "${latestPublicMessage.content.substring(0, 50)}${latestPublicMessage.content.length > 50 ? '...' : ''}"`
    : 'The challenge begins... Agents are analyzing the ARC grid...';

  if (data.game.is_merged) {
    // Merged: Horizontal layout
    return (
      <div className="h-full flex flex-col">
        <div className="flex-grow flex items-center justify-center gap-4 flex-wrap">
          {activeAgents.map(agent => (
            <AgentSprite key={agent.agent_id} agent={agent} />
          ))}
        </div>
        <div className="mt-auto">
          <DialogBox text={dialogText} />
        </div>
      </div>
    );
  }

  // Pre-merge: Diagonal split
  return (
    <div className="h-full flex flex-col relative">
      {/* Team Beta - Top Right */}
      <div className="absolute top-4 right-4 flex flex-col items-end gap-2">
        <span className="text-pkmn-red text-[10px] font-bold">TEAM BETA</span>
        <div className="flex flex-wrap justify-end gap-2 max-w-[200px]">
          {teamBeta.map(agent => (
            <AgentSprite key={agent.agent_id} agent={agent} />
          ))}
        </div>
      </div>
      
      {/* VS Badge */}
      <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2">
        <div className="bg-pkmn-gold text-gbc-black px-4 py-2 border-4 border-gbc-black font-bold text-lg">
          VS
        </div>
      </div>
      
      {/* Team Alpha - Bottom Left */}
      <div className="absolute bottom-16 left-4 flex flex-col items-start gap-2">
        <span className="text-pkmn-blue text-[10px] font-bold">TEAM ALPHA</span>
        <div className="flex flex-wrap gap-2 max-w-[200px]">
          {teamAlpha.map(agent => (
            <AgentSprite key={agent.agent_id} agent={agent} />
          ))}
        </div>
      </div>
      
      {/* Dialog */}
      <div className="mt-auto">
        <DialogBox text={dialogText} />
      </div>
    </div>
  );
}
