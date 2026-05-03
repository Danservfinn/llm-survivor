"use client";

import { useState, useEffect } from 'react';
import { ApiStateResponse } from '@/types';
import { AgentSprite } from '@/components/common/AgentSprite';
import { DialogBox } from '@/components/common/DialogBox';

interface PhaseDMemoryProps {
  data: ApiStateResponse;
}

export function PhaseDMemory({ data }: PhaseDMemoryProps) {
  const [activeIndex, setActiveIndex] = useState(0);
  
  const activeAgents = data.agents.filter(a => a.status === 'active');
  
  useEffect(() => {
    if (activeAgents.length === 0) return;
    
    const intervalId = setInterval(() => {
      setActiveIndex(prev => (prev + 1) % activeAgents.length);
    }, 25000); // Increased to 25000 to allow typewriter to finish 150 words
    
    return () => clearInterval(intervalId);
  }, [activeAgents.length]);
  
  const currentAgent = activeAgents[activeIndex];
  
  if (!currentAgent) {
    return (
      <div className="h-full flex items-center justify-center bg-pkmn-blue">
        <span className="text-white">No active agents</span>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col items-center justify-center bg-pkmn-blue p-4">
      {/* Title */}
      <div className="absolute top-4 left-4">
        <span className="text-white text-[10px] bg-gbc-black px-2 py-1">
          BILL&apos;S PC - CONFESSIONAL ARCHIVE
        </span>
      </div>
      
      {/* Agent Counter */}
      <div className="absolute top-4 right-4">
        <span className="text-white text-[10px]">
          Agent {activeIndex + 1} of {activeAgents.length}
        </span>
      </div>
      
      {/* Large Agent Sprite */}
      <div className="mb-6">
        <AgentSprite agent={currentAgent} scale={3} />
      </div>
      
      {/* Agent Info */}
      <div className="text-center mb-4">
        <h3 className="text-white text-lg font-bold mb-1">{currentAgent.pseudonym}</h3>
        <span className="text-gbc-bg text-[10px]">{currentAgent.team_id}</span>
      </div>
      
      {/* Memory Display */}
      <div className="w-full max-w-2xl">
        <DialogBox 
          text={currentAgent.confessional_memory || `${currentAgent.pseudonym} has no recorded memories...`} 
        />
      </div>
      
      {/* Progress Dots */}
      <div className="flex gap-1 mt-4">
        {activeAgents.map((_, index) => (
          <div
            key={index}
            className={`w-2 h-2 rounded-full ${
              index === activeIndex ? 'bg-pkmn-gold' : 'bg-white/30'
            }`}
          />
        ))}
      </div>
    </div>
  );
}
