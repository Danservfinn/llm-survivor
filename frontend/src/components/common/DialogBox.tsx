"use client";

import { useState, useEffect, useRef } from 'react';

interface AudioWindow extends Window {
  webkitAudioContext?: typeof AudioContext;
}

// Zero-dependency 8-bit blip generator
const playBlip = () => {
  try {
    const AudioContextConstructor = window.AudioContext || (window as AudioWindow).webkitAudioContext;
    if (!AudioContextConstructor) return;
    const ctx = new AudioContextConstructor();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'square';
    osc.frequency.setValueAtTime(400 + Math.random() * 100, ctx.currentTime);
    gain.gain.setValueAtTime(0.015, ctx.currentTime);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.03);
  } catch {
    /* Ignore audio policy blocks */
  }
};

interface DialogBoxProps {
  text: string;
}

export function DialogBox({ text }: DialogBoxProps) {
  const [displayedText, setDisplayedText] = useState('');
  const [isComplete, setIsComplete] = useState(false);
  const audioEnabled = useRef(false);

  // Unlock audio context on first click anywhere
  useEffect(() => {
    const enableAudio = () => {
      audioEnabled.current = true;
    };
    window.addEventListener('click', enableAudio, { once: true });
    return () => window.removeEventListener('click', enableAudio);
  }, []);

  useEffect(() => {
    // Reset when text changes
    setDisplayedText('');
    setIsComplete(false);
    
    let currentIndex = 0;
    
    const intervalId = setInterval(() => {
      if (currentIndex < text.length) {
        setDisplayedText(text.slice(0, currentIndex + 1));
        
        // Play blip every 3 characters to sound like GBC text
        if (audioEnabled.current && currentIndex % 3 === 0 && text[currentIndex] !== ' ') {
          playBlip();
        }
        
        currentIndex++;
      } else {
        setIsComplete(true);
        clearInterval(intervalId);
      }
    }, 20);

    return () => clearInterval(intervalId);
  }, [text]);

  return (
    <div className="gbc-box p-4 min-h-[100px] relative bg-white">
      <p className="text-[10px] leading-relaxed text-gbc-black">
        {displayedText}
        {isComplete && (
          <span className="inline-block ml-1 animate-bounce">▼</span>
        )}
      </p>
    </div>
  );
}
