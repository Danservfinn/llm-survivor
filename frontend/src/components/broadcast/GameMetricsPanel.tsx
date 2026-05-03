"use client";

import { Activity, Brain, Database, MessageCircle, Radar, Shield, Target, Timer, Trophy, Users } from "lucide-react";

import type { Agent, ApiStateResponse, GameSummary, StoryEvent } from "@/types";

interface GameMetricsPanelProps {
  state: ApiStateResponse | null;
  summary: GameSummary | null;
  events: StoryEvent[];
  currentIndex: number;
  runtimeLabel: string;
}

interface DynamicNote {
  label: string;
  value: string;
}

function formatSlug(value?: string | null) {
  return value?.replaceAll("_", " ") ?? "waiting";
}

function getAgentName(agentId: string | null | undefined, agents: Agent[]) {
  if (!agentId) {
    return "Unknown";
  }

  return agents.find((agent) => agent.agent_id === agentId)?.pseudonym ?? agentId;
}

function readString(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function readVoteAnalysis(payload: Record<string, unknown>) {
  const value = payload.ui_vote_analysis;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const analysis = value as Record<string, unknown>;
  const because = readString(analysis, "because");
  const risk = readString(analysis, "risk");
  const intendedOutcome = readString(analysis, "intended_outcome");
  if (!because || !risk || !intendedOutcome) {
    return null;
  }
  return `UI analysis: Because ${because}. Risk: ${risk} Intended outcome: ${intendedOutcome}`;
}

function getReplayStatus(agent: Agent, visibleEvents: StoryEvent[]) {
  const visibleElimination = visibleEvents.some(
    (event) =>
      event.kind === "elimination" &&
      (event.actor_ids.includes(agent.agent_id) || event.target_ids.includes(agent.agent_id)),
  );

  if (visibleElimination) {
    return "eliminated";
  }

  return agent.has_immunity ? "immune" : "active";
}

function getReplayFocus(agent: Agent, visibleEvents: StoryEvent[], state: ApiStateResponse) {
  const visibleVote = [...visibleEvents]
    .reverse()
    .find((event) => event.kind === "vote_booth" && event.actor_ids.includes(agent.agent_id));
  const voteTarget = visibleVote
    ? readString(visibleVote.payload, "vote_target_name") ?? getAgentName(visibleVote.target_ids[0], state.agents)
    : null;
  const voteExplanation = visibleVote ? readString(visibleVote.payload, "vote_explanation") : null;
  const voteAnalysis = visibleVote ? readVoteAnalysis(visibleVote.payload) : null;

  if (voteTarget) {
    return `Voting ${voteTarget}${voteExplanation ? `: ${voteExplanation}` : ""}${voteAnalysis ? ` ${voteAnalysis}` : ""}`;
  }

  const visibleAgentBeat = [...visibleEvents]
    .reverse()
    .find((event) => event.actor_ids.includes(agent.agent_id) && event.kind !== "vote_reveal");

  if (visibleAgentBeat?.inner_thought) {
    return visibleAgentBeat.inner_thought;
  }

  if (visibleAgentBeat?.dialogue) {
    return visibleAgentBeat.dialogue;
  }

  return "Reading the room for the next opening.";
}

function buildDynamics(state: ApiStateResponse, events: StoryEvent[], currentEvent: StoryEvent | null): DynamicNote[] {
  const notes: DynamicNote[] = [];
  const voteEvents = events.filter((event) => event.kind === "vote_booth");
  const voteCounts = new Map<string, number>();

  voteEvents.forEach((event) => {
    const targetName = readString(event.payload, "vote_target_name") ?? getAgentName(event.target_ids[0], state.agents);
    voteCounts.set(targetName, (voteCounts.get(targetName) ?? 0) + 1);
  });

  const votePressure = [...voteCounts.entries()].sort((a, b) => b[1] - a[1]);
  const activeAgents = state.agents.filter((agent) => agent.status === "active");
  const immuneAgents = activeAgents.filter((agent) => Boolean(agent.has_immunity));
  const atRiskAgents = activeAgents.filter((agent) => !Boolean(agent.has_immunity));

  if (currentEvent) {
    notes.push({
      label: "Current pressure",
      value: `${currentEvent.title}: ${currentEvent.dialogue}`,
    });
  }

  if (immuneAgents.length > 0) {
    notes.push({
      label: "Immunity",
      value: `${immuneAgents.map((agent) => agent.pseudonym).join(", ")} cannot receive votes this round, narrowing the target pool to ${atRiskAgents.length}.`,
    });
  }

  if (votePressure.length > 0) {
    const [target, count] = votePressure[0];
    notes.push({
      label: "Vote math",
      value: `${target} has the most visible pressure with ${count} of ${voteEvents.length} votes shown so far.`,
    });
  }

  if (votePressure.length > 1) {
    const [target, count] = votePressure[1];
    notes.push({
      label: "Counterpath",
      value: `${target} is the alternate landing spot with ${count} vote${count === 1 ? "" : "s"} shown.`,
    });
  }

  const motiveEvent = [...voteEvents].reverse().find((event) => readString(event.payload, "vote_explanation"));
  const motive = motiveEvent ? readString(motiveEvent.payload, "vote_explanation") : null;
  if (motive && motiveEvent) {
    const analysis = readVoteAnalysis(motiveEvent.payload);
    notes.push({
      label: "Motive trail",
      value: `${getAgentName(motiveEvent.actor_ids[0], state.agents)}: ${motive}${analysis ? ` ${analysis}` : ""}`,
    });
  }

  if (notes.length === 0) {
    notes.push({
      label: "Game read",
      value: "The round has not produced enough visible signal yet. Watch the next conversation or vote for the first pressure point.",
    });
  }

  return notes.slice(0, 5);
}

export function GameMetricsPanel({ state, summary, events, currentIndex, runtimeLabel }: GameMetricsPanelProps) {
  if (!state) {
    return <div className="empty-panel">Waiting for backend state.</div>;
  }

  const currentEvent = events[currentIndex] ?? null;
  const progressPercent = events.length > 0 ? ((currentIndex + 1) / events.length) * 100 : 0;
  const visibleEvents = events.slice(0, currentIndex + 1);
  const dynamics = buildDynamics(state, visibleEvents, currentEvent);
  const latestChallenge = summary?.round_history
    .map((round) => round.challenge_result)
    .filter(Boolean)
    .at(-1) as Record<string, unknown> | undefined;
  const immunityNames = state.agents.filter((agent) => Boolean(agent.has_immunity)).map((agent) => agent.pseudonym);
  const winnerName = summary?.winner?.pseudonym ?? null;

  return (
    <div className="metrics-panel">
      <section className="debug-card replay-timeline-card">
        <h2>
          <Activity size={16} />
          Game Metrics
        </h2>
        <div className="timeline-meter" aria-label="Replay timeline">
          <span style={{ width: `${progressPercent}%` }} />
        </div>
        <dl>
          <div>
            <dt>Replay Beat</dt>
            <dd>{events.length > 0 ? `${currentIndex + 1}/${events.length}` : "0/0"}</dd>
          </div>
          <div>
            <dt>Current Scene</dt>
            <dd>{formatSlug(currentEvent?.scene)}</dd>
          </div>
          <div>
            <dt>Current Beat</dt>
            <dd>{formatSlug(currentEvent?.kind)}</dd>
          </div>
          <div>
            <dt>Runtime</dt>
            <dd>{runtimeLabel}</dd>
          </div>
          <div>
            <dt>LLM Calls</dt>
            <dd>{state.llm?.openrouter_configured ? "live" : "needs key"}</dd>
          </div>
          <div>
            <dt>Challenge Result</dt>
            <dd>
              {latestChallenge && typeof latestChallenge.winning_agent_id === "string"
                ? getAgentName(latestChallenge.winning_agent_id, state.agents)
                : "pending"}
            </dd>
          </div>
          <div>
            <dt>Path To Finale</dt>
            <dd>
              {summary
                ? summary.finale_status.winner_declared
                  ? "complete"
                  : `${summary.finale_status.remaining_eliminations_to_finale} eliminations`
                : "calculating"}
            </dd>
          </div>
          <div>
            <dt>Next Round Prep</dt>
            <dd>
              {state.next_round_preload
                ? `R${state.next_round_preload.target_round} ${formatSlug(state.next_round_preload.status)}`
                : "not queued"}
            </dd>
          </div>
        </dl>
        {state.next_round_preload && (
          <p className="timeline-now">
            <Brain size={13} />
            {state.next_round_preload.status === "complete"
              ? `Round ${state.next_round_preload.target_round} responses are buffered.`
              : `Preparing round ${state.next_round_preload.target_round} responses in the background.`}
          </p>
        )}
        {state.llm && !state.llm.openrouter_configured && (
          <p className="timeline-now">
            <Brain size={13} />
            Backend needs an OpenRouter API key before live model calls run.
          </p>
        )}
        {currentEvent && (
          <p className="timeline-now">
            <Timer size={13} />
            {currentEvent.title}
          </p>
        )}
      </section>

      {(latestChallenge || immunityNames.length > 0 || winnerName) && (
        <section className="debug-card season-result-card">
          <h2>
            <Shield size={16} />
            Round Stakes
          </h2>
          <dl>
            <div>
              <dt>Immunity</dt>
              <dd>{immunityNames.length > 0 ? immunityNames.join(", ") : "pending"}</dd>
            </div>
            <div>
              <dt>Challenge Source</dt>
              <dd>
                {latestChallenge && typeof latestChallenge.status === "string"
                  ? formatSlug(latestChallenge.status)
                  : "pending"}
              </dd>
            </div>
            <div>
              <dt>Winner</dt>
              <dd>{winnerName ?? "not declared"}</dd>
            </div>
          </dl>
        </section>
      )}

      {summary && summary.eliminated_jury.length > 0 && (
        <section className="debug-card jury-card">
          <h2>
            <Trophy size={16} />
            Jury And Finale
          </h2>
          <div className="agent-table">
            {summary.eliminated_jury.map((agent) => (
              <div key={agent.agent_id} className="agent-row eliminated">
                <strong>{agent.pseudonym}</strong>
                <span>jury</span>
              </div>
            ))}
            {summary.finale_status.finalists.map((agent) => (
              <div key={agent.agent_id} className="agent-row">
                <strong>{agent.pseudonym}</strong>
                <span>finalist</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="debug-card dynamics-card">
        <h2>
          <Radar size={16} />
          Dynamics at Play
        </h2>
        <div className="dynamics-list">
          {dynamics.map((note) => (
            <article key={note.label} className="dynamic-item">
              <strong>{note.label}</strong>
              <p>{note.value}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="debug-card agent-focus-card">
        <h2>
          <Target size={16} />
          Top of Mind
        </h2>
        <div className="agent-focus-list">
          {state.agents.map((agent) => {
            const replayStatus = getReplayStatus(agent, visibleEvents);
            const focus = getReplayFocus(agent, visibleEvents, state);

            return (
              <article key={agent.agent_id} className={replayStatus === "eliminated" ? "agent-focus-item eliminated" : "agent-focus-item"}>
                <header>
                  <strong>{agent.pseudonym}</strong>
                  <span>{replayStatus}</span>
                </header>
                <p>{focus}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="debug-card retro-debug">
        <h2>
          <Database size={16} />
          Game State
        </h2>
        <dl>
          <div>
            <dt>Phase</dt>
            <dd>{state.game.phase}</dd>
          </div>
          <div>
            <dt>Step</dt>
            <dd>{state.game.phase_step}</dd>
          </div>
          <div>
            <dt>Turns</dt>
            <dd>{state.turn_count}</dd>
          </div>
          <div>
            <dt>Events</dt>
            <dd>{state.story_event_count}</dd>
          </div>
        </dl>
      </section>

      <section className="debug-card">
        <h2>
          <Users size={16} />
          Agent Status
        </h2>
        <div className="agent-table">
          {state.agents.map((agent) => (
            <div key={agent.agent_id} className={agent.status === "eliminated" ? "agent-row eliminated" : "agent-row"}>
              <strong>{agent.pseudonym}</strong>
              <span>{agent.has_immunity ? "immune" : agent.status}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="debug-card god-feed">
        <h2>
          <Brain size={16} />
          Private Signal
        </h2>
        {state.messages.length === 0 ? (
          <p>No inner thoughts recorded yet.</p>
        ) : (
          state.messages.slice(0, 12).map((message) => (
            <article key={message.id}>
              <header>
                <MessageCircle size={13} />
                <strong>{getAgentName(message.sender_id, state.agents)}</strong>
                <span>Turn {message.turn_index}</span>
              </header>
              <p>{message.content}</p>
              {message.inner_thought && <blockquote>{message.inner_thought}</blockquote>}
            </article>
          ))
        )}
      </section>

      <section className="debug-card">
        <h2>Recent Story Events</h2>
        <pre>{JSON.stringify(events.slice(-5), null, 2)}</pre>
      </section>
    </div>
  );
}
