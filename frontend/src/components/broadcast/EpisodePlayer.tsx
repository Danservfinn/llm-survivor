"use client";

import { motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, Radio, Sparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { DirectorControls } from "@/components/broadcast/DirectorControls";
import { GameMetricsPanel } from "@/components/broadcast/GameMetricsPanel";
import { SceneStage } from "@/components/broadcast/SceneStage";
import type {
  ApiStateResponse,
  EpisodeResponse,
  GameSummary,
  ModelRoster,
  NextRoundPreloadStatus,
  StoryEvent,
  ViewerState,
  VoiceTimelineLine,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  return response.json() as Promise<T>;
}

function resolveAudioUrl(audioUrl: string) {
  return audioUrl.startsWith("http") ? audioUrl : `${API_BASE}${audioUrl}`;
}

function playableTimeline(event: StoryEvent): VoiceTimelineLine[] {
  return (event.payload.voice_timeline ?? []).filter(
    (line) => line.status === "ready" && typeof line.audio_url === "string" && line.audio_url.length > 0,
  );
}

export function EpisodePlayer() {
  const reducedMotion = useReducedMotion();
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const nextRoundPreloadRequestedRef = useRef(false);
  const lastViewerStateRef = useRef<string | null>(null);
  const [episode, setEpisode] = useState<EpisodeResponse | null>(null);
  const [state, setState] = useState<ApiStateResponse | null>(null);
  const [summary, setSummary] = useState<GameSummary | null>(null);
  const [rosters, setRosters] = useState<ModelRoster[]>([]);
  const [selectedRoster, setSelectedRoster] = useState("default");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [episodeData, stateData, summaryData, rosterData] = await Promise.all([
      fetchJson<EpisodeResponse>("/api/episode/current?include_audio=true"),
      fetchJson<ApiStateResponse>("/api/state"),
      fetchJson<GameSummary>("/api/game/summary"),
      fetchJson<{ rosters: ModelRoster[] }>("/api/model-rosters"),
    ]);
    setEpisode(episodeData);
    setState(stateData);
    setSummary(summaryData);
    setRosters(rosterData.rosters);
    const viewerState = stateData.viewer_state;
    if (viewerState) {
      lastViewerStateRef.current = viewerState.updated_at;
      setCurrentIndex(
        episodeData.events.length === 0
          ? 0
          : Math.min(viewerState.replay_index, episodeData.events.length - 1),
      );
      setIsPlaying(viewerState.is_playing && episodeData.events.length > 0);
    } else {
      setCurrentIndex((index) =>
        episodeData.events.length === 0 ? 0 : Math.min(index, episodeData.events.length - 1),
      );
    }
    return episodeData;
  }, []);

  useEffect(() => {
    refresh().catch((refreshError: Error) => setError(refreshError.message));
  }, [refresh]);

  const events = episode?.events ?? [];
  const currentEvent: StoryEvent | null = events[currentIndex] ?? null;
  const nextRoundPreload = state?.next_round_preload ?? null;

  const persistViewerState = useCallback(async (replayIndex: number, playing: boolean) => {
    const viewerResponse = await fetchJson<{ viewer_state: ViewerState }>("/api/viewer-state", {
      method: "POST",
      body: JSON.stringify({
        replay_index: Math.max(0, replayIndex),
        is_playing: playing,
        round_number: episode?.round ?? state?.game.current_round ?? 7,
        phase: episode?.phase ?? state?.game.phase ?? "round",
      }),
    });
    lastViewerStateRef.current = viewerResponse.viewer_state.updated_at;
    setState((previousState) =>
      previousState ? { ...previousState, viewer_state: viewerResponse.viewer_state } : previousState,
    );
    return viewerResponse.viewer_state;
  }, [episode?.phase, episode?.round, state?.game.current_round, state?.game.phase]);

  const setSharedPlayback = useCallback((nextIndex: number, playing: boolean) => {
    const clampedIndex = events.length === 0 ? 0 : Math.min(Math.max(0, nextIndex), events.length - 1);
    const shouldPlay = playing && events.length > 0 && clampedIndex < events.length - 1;
    setCurrentIndex(clampedIndex);
    setIsPlaying(shouldPlay);
    persistViewerState(clampedIndex, shouldPlay).catch((viewerError: Error) => setError(viewerError.message));
  }, [events.length, persistViewerState]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      fetchJson<{ viewer_state: ViewerState }>("/api/viewer-state")
        .then(({ viewer_state }) => {
          const changed =
            viewer_state.updated_at !== lastViewerStateRef.current ||
            viewer_state.replay_index !== currentIndex ||
            viewer_state.is_playing !== isPlaying;
          if (!changed) {
            return;
          }
          lastViewerStateRef.current = viewer_state.updated_at;
          const clampedIndex =
            events.length === 0 ? 0 : Math.min(Math.max(0, viewer_state.replay_index), events.length - 1);
          setCurrentIndex(clampedIndex);
          setIsPlaying(viewer_state.is_playing && events.length > 0 && clampedIndex < events.length - 1);
          setState((previousState) =>
            previousState ? { ...previousState, viewer_state } : previousState,
          );
        })
        .catch((viewerError: Error) => setError(viewerError.message));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [currentIndex, events.length, isPlaying]);

  useEffect(() => {
    if (!nextRoundPreload || !["pending", "running"].includes(nextRoundPreload.status)) {
      return;
    }
    const timer = window.setInterval(() => {
      fetchJson<ApiStateResponse>("/api/state")
        .then((stateData) => setState(stateData))
        .catch((statusError: Error) => setError(statusError.message));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [nextRoundPreload]);

  const requestNextRoundPreload = useCallback(() => {
    if (nextRoundPreloadRequestedRef.current || events.length === 0) {
      return;
    }
    nextRoundPreloadRequestedRef.current = true;
    fetchJson<{ preload: NextRoundPreloadStatus | null }>("/api/rounds/preload-next", { method: "POST" })
      .then(() => fetchJson<ApiStateResponse>("/api/state"))
      .then((stateData) => setState(stateData))
      .catch((preloadError: Error) => {
        nextRoundPreloadRequestedRef.current = false;
        setError(preloadError.message);
      });
  }, [events.length]);

  useEffect(() => {
    if (!isPlaying || !currentEvent || events.length === 0) {
      activeAudioRef.current?.pause();
      activeAudioRef.current = null;
      return;
    }
    if (currentIndex >= events.length - 1) {
      setSharedPlayback(currentIndex, false);
      return;
    }

    const timers: number[] = [];
    const audioTimeline = playableTimeline(currentEvent);
    const stopActiveAudio = () => {
      activeAudioRef.current?.pause();
      activeAudioRef.current = null;
    };
    stopActiveAudio();

    for (const line of audioTimeline) {
      timers.push(
        window.setTimeout(() => {
          stopActiveAudio();
          const audio = new Audio(resolveAudioUrl(line.audio_url as string));
          activeAudioRef.current = audio;
          audio.play().catch(() => {
            activeAudioRef.current = null;
          });
        }, Math.max(0, line.start_ms)),
      );
    }

    const voiceDuration = audioTimeline.length > 0 ? audioTimeline[audioTimeline.length - 1].end_ms : 0;
    const playbackDelay =
      audioTimeline.length > 0
        ? Math.max(1200, voiceDuration + 500)
        : reducedMotion
          ? Math.min(900, currentEvent.duration_ms)
          : Math.max(1200, Math.min(currentEvent.duration_ms, 14000));
    timers.push(window.setTimeout(() => {
      stopActiveAudio();
      setSharedPlayback(currentIndex + 1, currentIndex + 1 < events.length - 1);
    }, playbackDelay));
    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
      stopActiveAudio();
    };
  }, [currentEvent, currentIndex, events.length, isPlaying, reducedMotion, setSharedPlayback]);

  const runtimeLabel = useMemo(() => {
    const totalSeconds = Math.round((episode?.runtime_ms ?? 0) / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  }, [episode?.runtime_ms]);

  async function runAction(action: () => Promise<EpisodeResponse | void>) {
    setIsBusy(true);
    setError(null);
    try {
      await action();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : String(actionError));
    } finally {
      setIsBusy(false);
    }
  }

  const handleAdvanceTurn = () =>
    runAction(async () => {
      const previousLength = events.length;
      await fetchJson("/api/turns/advance", { method: "POST" });
      const nextEpisode = await refresh();
      setSharedPlayback(Math.max(0, Math.min(previousLength, nextEpisode.events.length - 1)), false);
    });

  const handleAutoRun = () =>
    runAction(async () => {
      await fetchJson("/api/turns/auto-run", {
        method: "POST",
        body: JSON.stringify({ max_turns: 40 }),
      });
      const nextEpisode = await refresh();
      setSharedPlayback(nextEpisode.events.length > 0 ? 0 : currentIndex, false);
    });

  const handleRunToFinale = () =>
    runAction(async () => {
      await fetchJson("/api/game/auto-run-to-end", {
        method: "POST",
        body: JSON.stringify({
          max_rounds: 8,
          max_turns: 260,
          max_live_calls: 220,
          max_estimated_cost_cents: 500,
        }),
      });
      const nextEpisode = await refresh();
      setSharedPlayback(nextEpisode.events.length > 0 ? 0 : currentIndex, false);
      nextRoundPreloadRequestedRef.current = false;
    });

  const handleNextRound = () =>
    runAction(async () => {
      await fetchJson("/api/rounds/next", { method: "POST" });
      await refresh();
      nextRoundPreloadRequestedRef.current = false;
    });

  const handleReset = () =>
    runAction(async () => {
      await fetchJson("/api/dev/reset", {
        method: "POST",
        body: JSON.stringify({
          roster_preset: selectedRoster === "default" ? null : selectedRoster,
        }),
      });
      await refresh();
      setSharedPlayback(0, false);
      nextRoundPreloadRequestedRef.current = false;
    });

  const activeAgents = state?.agents.filter((agent) => agent.status === "active").length ?? 0;
  const totalAgents = state?.agents.length ?? 6;
  const phaseStep = state?.game.phase_step ?? "loading";
  const replayBeatLabel =
    events.length > 0 ? `${String(currentIndex + 1).padStart(2, "0")}/${String(events.length).padStart(2, "0")}` : "00/00";
  const nextRoundLabel =
    nextRoundPreload
      ? `R${nextRoundPreload.target_round} ${nextRoundPreload.status}`
      : "not queued";

  return (
    <main className="broadcast-shell">
      <section className="broadcast-header" aria-label="Episode status">
        <div>
          <div className="eyebrow">
            <Radio size={14} />
            Episode Replay
          </div>
          <h1>{episode?.title ?? "Round 7: Challenge to Tribal Conference"}</h1>
        </div>
        <div className="broadcast-meta">
          <div className="provider-status" aria-label="LLM response mode">
            <span>LLM Response Mode</span>
            <strong className={state?.llm?.openrouter_configured ? "live" : "needs-key"}>
              <Sparkles size={15} />
              Live OpenRouter
              {state?.llm && !state.llm.openrouter_configured && <small>Needs key</small>}
            </strong>
          </div>
          <dl className="status-strip">
            <div>
              <dt>Round</dt>
              <dd>{state?.game.current_round ?? 7}</dd>
            </div>
            <div>
              <dt>Game Turn</dt>
              <dd>{state?.game.turn_index ?? 0}</dd>
            </div>
            <div>
              <dt>Replay Beat</dt>
              <dd>{replayBeatLabel}</dd>
            </div>
            <div>
              <dt>Step</dt>
              <dd>{phaseStep.replaceAll("_", " ")}</dd>
            </div>
            <div>
              <dt>Active</dt>
              <dd>{activeAgents}/{totalAgents}</dd>
            </div>
            <div>
              <dt>Runtime</dt>
              <dd>{runtimeLabel}</dd>
            </div>
            <div>
              <dt>Next Round</dt>
              <dd>{nextRoundLabel}</dd>
            </div>
          </dl>
        </div>
      </section>

      {error && (
        <motion.div
          className="error-banner"
          role="alert"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <AlertTriangle size={16} />
          <span>{error}</span>
        </motion.div>
      )}

      <section className="broadcast-layout">
        <div className="stage-column">
          <SceneStage event={currentEvent} agents={episode?.agents ?? []} reducedMotion={Boolean(reducedMotion)} />
          <DirectorControls
            isPlaying={isPlaying}
            isBusy={isBusy}
            canPlay={events.length > 0}
            currentIndex={currentIndex}
            totalEvents={events.length}
            currentEvent={currentEvent}
            onPlayPause={() => {
              const nextPlaying = !isPlaying;
              if (nextPlaying) {
                requestNextRoundPreload();
              }
              setSharedPlayback(currentIndex, nextPlaying);
            }}
            onRestart={() => setSharedPlayback(0, false)}
            onStepBack={() => setSharedPlayback(currentIndex - 1, false)}
            onStepForward={() => setSharedPlayback(currentIndex + 1, false)}
            onSkipToEnd={() => setSharedPlayback(Math.max(0, events.length - 1), false)}
            onScrub={(index) => setSharedPlayback(index, false)}
            onAdvanceTurn={handleAdvanceTurn}
            onAutoRun={handleAutoRun}
            onRunToFinale={handleRunToFinale}
            onNextRound={handleNextRound}
            onReset={handleReset}
            rosters={rosters}
            selectedRoster={selectedRoster}
            onRosterChange={setSelectedRoster}
          />
        </div>

        <aside className="control-column metrics-column" aria-label="Game metrics and state">
          <GameMetricsPanel
            state={state}
            summary={summary}
            events={events}
            currentIndex={currentIndex}
            runtimeLabel={runtimeLabel}
          />
        </aside>
      </section>
    </main>
  );
}
