"use client";

import {
  ChevronsRight,
  FastForward,
  Flag,
  Pause,
  Play,
  RefreshCcw,
  RotateCcw,
  SkipBack,
  SkipForward,
  StepForward,
  Trophy,
} from "lucide-react";

import type { ModelRoster, StoryEvent } from "@/types";

interface DirectorControlsProps {
  isPlaying: boolean;
  isBusy: boolean;
  canPlay: boolean;
  currentIndex: number;
  totalEvents: number;
  currentEvent: StoryEvent | null;
  onPlayPause: () => void;
  onRestart: () => void;
  onStepBack: () => void;
  onStepForward: () => void;
  onSkipToEnd: () => void;
  onScrub: (index: number) => void;
  onAdvanceTurn: () => void;
  onAutoRun: () => void;
  onRunToFinale: () => void;
  onNextRound: () => void;
  onReset: () => void;
  rosters: ModelRoster[];
  selectedRoster: string;
  onRosterChange: (rosterId: string) => void;
}

export function DirectorControls({
  isPlaying,
  isBusy,
  canPlay,
  currentIndex,
  totalEvents,
  currentEvent,
  onPlayPause,
  onRestart,
  onStepBack,
  onStepForward,
  onSkipToEnd,
  onScrub,
  onAdvanceTurn,
  onAutoRun,
  onRunToFinale,
  onNextRound,
  onReset,
  rosters,
  selectedRoster,
  onRosterChange,
}: DirectorControlsProps) {
  const atStart = currentIndex <= 0;
  const atEnd = totalEvents === 0 || currentIndex >= totalEvents - 1;

  return (
    <div className="director-controls" aria-label="Episode controls">
      <div className="transport-row">
        <button type="button" onClick={onRestart} disabled={!canPlay || atStart} aria-label="Restart">
          <RotateCcw size={18} />
        </button>
        <button type="button" onClick={onStepBack} disabled={!canPlay || atStart} aria-label="Previous beat">
          <SkipBack size={18} />
        </button>
        <button type="button" className="play-button" onClick={onPlayPause} disabled={!canPlay} aria-label="Play or pause">
          {isPlaying ? <Pause size={22} /> : <Play size={22} />}
          <span>{isPlaying ? "Pause" : "Play"}</span>
        </button>
        <button type="button" onClick={onStepForward} disabled={!canPlay || atEnd} aria-label="Next beat">
          <SkipForward size={18} />
        </button>
        <button type="button" onClick={onSkipToEnd} disabled={!canPlay || atEnd} aria-label="Skip to end">
          <FastForward size={18} />
        </button>
      </div>

      <label className="scrub-row">
        <span>{String(currentIndex + (totalEvents ? 1 : 0)).padStart(2, "0")}</span>
        <input
          type="range"
          min={0}
          max={Math.max(0, totalEvents - 1)}
          value={Math.min(currentIndex, Math.max(0, totalEvents - 1))}
          disabled={!canPlay}
          onChange={(event) => onScrub(Number(event.target.value))}
        />
        <span>{String(totalEvents).padStart(2, "0")}</span>
      </label>

      <div className="action-row">
        <button type="button" className="command-button" onClick={onAdvanceTurn} disabled={isBusy}>
          <StepForward size={16} />
          Next Turn
        </button>
        <button type="button" className="command-button primary" onClick={onAutoRun} disabled={isBusy}>
          <ChevronsRight size={16} />
          Build Round
        </button>
        <button type="button" className="command-button" onClick={onRunToFinale} disabled={isBusy}>
          <Trophy size={16} />
          Run To Finale
        </button>
        <button type="button" className="command-button" onClick={onNextRound} disabled={isBusy}>
          <Flag size={16} />
          Next Round
        </button>
      </div>

      <div className="roster-row">
        <label>
          <span>Roster</span>
          <select value={selectedRoster} onChange={(event) => onRosterChange(event.target.value)} disabled={isBusy}>
            {(rosters.length > 0 ? rosters : [{ id: "default", name: "Default Benchmark Models", models: [] }]).map((roster) => (
              <option key={roster.id} value={roster.id}>
                {roster.name}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="command-button ghost" onClick={onReset} disabled={isBusy}>
          <RefreshCcw size={16} />
          Reset
        </button>
      </div>

      <div className="now-playing" aria-live="polite">
        <span>Replay Beat</span>
        <strong>{currentEvent?.title ?? "No event loaded"}</strong>
      </div>
    </div>
  );
}
