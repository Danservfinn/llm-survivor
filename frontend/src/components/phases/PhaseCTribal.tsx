"use client";

import { useState, useEffect, useMemo } from 'react';
import { ApiStateResponse } from '@/types';
import { AgentSprite } from '@/components/common/AgentSprite';
import { DialogBox } from '@/components/common/DialogBox';

interface PhaseCTribalProps {
  data: ApiStateResponse;
}

export function PhaseCTribal({ data }: PhaseCTribalProps) {
  const [revealedVoteIndex, setRevealedVoteIndex] = useState(-1);
  
  const activeAgents = data.agents.filter(a => a.status === 'active');
  const vulnerableAgents = activeAgents.filter(a => !a.has_immunity);
  const immuneAgents = activeAgents.filter(a => a.has_immunity);
  
  const votes = useMemo(() => data.votes ?? [], [data.votes]);
  const votesLength = votes.length;
  const eliminatedAgentId = useMemo(() => {
    if (revealedVoteIndex !== votesLength - 1 || votesLength === 0) {
      return null;
    }

    const voteCounts: Record<string, number> = {};
    votes.forEach((vote) => {
      if (vote.target_id) {
        voteCounts[vote.target_id] = (voteCounts[vote.target_id] || 0) + 1;
      }
    });

    const maxVotes = Math.max(...Object.values(voteCounts));
    return Object.entries(voteCounts)
      .find(([, count]) => count === maxVotes)?.[0] ?? null;
  }, [revealedVoteIndex, votes, votesLength]);
  const eliminatedAgentName =
    data.agents.find((agent) => agent.agent_id === eliminatedAgentId)?.pseudonym ?? eliminatedAgentId;
  
  useEffect(() => {
    if (votesLength === 0) return;
    
    // Start revealing votes
    if (revealedVoteIndex < votesLength - 1) {
      const timer = setTimeout(() => {
        setRevealedVoteIndex(prev => prev + 1);
      }, 4000);
      
      return () => clearTimeout(timer);
    }
  }, [revealedVoteIndex, votesLength]);
  
  const currentVote = votes[revealedVoteIndex];
  const currentVoteLabel = currentVote?.target_pseudonym ?? currentVote?.target_id ?? 'hidden';
  const dialogText = currentVote 
    ? `The host reads the vote... It's for... ${currentVoteLabel.toUpperCase()}.`
    : revealedVoteIndex >= 0 && eliminatedAgentName
    ? `${eliminatedAgentName.toUpperCase()} has been voted out!`
    : 'The council result is ready... Reading the votes...';

  return (
    <div className="h-full flex flex-col bg-gbc-black p-4">
      {/* Title */}
      <div className="text-center mb-4">
        <h2 className="text-pkmn-red text-lg font-bold tracking-widest">TRIBAL CONFERENCE</h2>
      </div>
      
      {/* Vulnerable Agents (Center) */}
      <div className="flex-grow flex items-center justify-center gap-6">
        {vulnerableAgents.map(agent => (
          <AgentSprite 
            key={agent.agent_id} 
            agent={agent} 
            isFainting={eliminatedAgentId === agent.agent_id}
          />
        ))}
      </div>
      
      {/* Immune Agents (Faded, Background) */}
      {immuneAgents.length > 0 && (
        <div className="flex justify-center gap-4 mb-4 opacity-40">
          {immuneAgents.map(agent => (
            <AgentSprite key={agent.agent_id} agent={agent} />
          ))}
        </div>
      )}
      
      {/* Vote Counter */}
      {votes.length > 0 && (
        <div className="text-center mb-2">
          <span className="text-white text-[10px]">
            Vote {Math.min(revealedVoteIndex + 1, votes.length)} of {votes.length}
          </span>
        </div>
      )}
      
      {/* Dialog */}
      <DialogBox text={dialogText} />
    </div>
  );
}
