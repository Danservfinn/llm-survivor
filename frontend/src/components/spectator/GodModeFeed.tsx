"use client";

import { Message } from '@/types';
import { Brain, MessageCircle } from 'lucide-react';

interface GodModeFeedProps {
  messages: Message[];
  currentPhase: string;
}

export function GodModeFeed({ messages, currentPhase }: GodModeFeedProps) {
  // Sort by newest first and filter out spoilers during tribal
  const sortedMessages = [...messages]
    .sort((a, b) => b.id - a.id)
    .filter(msg => !(currentPhase === 'tribal' && msg.sender_id === 'SYSTEM' && msg.content.includes('voted out')));
  
  // Get the most recent trust score for display
  const getTrustScore = (msg: Message): number | null => {
    if (!msg.trust_telemetry || Object.keys(msg.trust_telemetry).length === 0) {
      return null;
    }
    const values = Object.values(msg.trust_telemetry);
    return values.length > 0 ? Math.round(values.reduce((a, b) => a + b, 0) / values.length) : null;
  };

  return (
    <div className="h-full overflow-y-auto pr-2">
      <div className="sticky top-0 bg-[#1a1a1a] z-10 pb-2 mb-2 border-b-2 border-gbc-bg">
        <h2 className="text-gbc-bg text-xs font-pixel flex items-center gap-2">
          <Brain size={14} />
          GOD MODE FEED
        </h2>
        <p className="text-[8px] text-gbc-primary mt-1">Inner thoughts exposed</p>
      </div>
      
      <div className="space-y-3">
        {sortedMessages.map((msg) => {
          const trustScore = getTrustScore(msg);
          
          return (
            <div key={msg.id} className="relative">
              {/* Trust Badge */}
              {trustScore !== null && (
                <div 
                  className={`absolute -top-2 -right-2 w-6 h-6 rounded-full flex items-center justify-center text-[8px] font-bold z-20 ${
                    trustScore >= 7 ? 'bg-gbc-primary text-gbc-black' :
                    trustScore >= 4 ? 'bg-pkmn-gold text-gbc-black' :
                    'bg-pkmn-red text-white'
                  }`}
                >
                  {trustScore}
                </div>
              )}
              
              {/* Brain (Inner Thought) */}
              <div className="bg-gbc-black text-gbc-bg p-3 rounded-t-sm relative text-[9px] leading-relaxed">
                <div className="flex items-start gap-2">
                  <Brain size={12} className="shrink-0 mt-0.5" />
                  <div>
                    <span className="text-pkmn-gold font-bold">{msg.sender_id}:</span>{' '}
                    {msg.inner_thought || '(No thought recorded)'}
                  </div>
                </div>
              </div>
              
              {/* Mouth (Public Action) */}
              <div className="gbc-box p-3 border-t-0 rounded-b-sm relative z-10 text-[9px] leading-relaxed bg-white">
                <div className="flex items-start gap-2">
                  <MessageCircle size={12} className="shrink-0 mt-0.5 text-gbc-dark" />
                  <div className="text-gbc-black">
                    {msg.is_public ? (
                      <span>📢 {msg.content || '*silence*'}</span>
                    ) : (
                      <span>🔒 Whisper to {msg.receiver_ids.join(', ')}: {msg.content || '*silent gesture*'}</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
