import type { Agent } from "@/types";

interface SpeechBubbleProps {
  speaker?: Agent;
  text?: string;
  align?: "left" | "right" | "center";
}

export function SpeechBubble({ speaker, text, align = "center" }: SpeechBubbleProps) {
  if (!text) {
    return null;
  }

  return (
    <div className={`speech-bubble speech-bubble-${align}`} aria-label={`${speaker?.pseudonym ?? "Speaker"} says`}>
      <p>{text}</p>
    </div>
  );
}
