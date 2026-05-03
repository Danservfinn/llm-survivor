export interface GameState {
  season_id: number;
  current_round: number;
  current_day?: number;
  turn_index: number;
  phase: 'round' | 'challenge' | 'scramble' | 'camp' | 'tribal' | 'memory' | 'finale' | 'completed' | 'finale_running';
  phase_step?: string;
  is_merged: boolean | number;
  winner: string | null;
  updated_at?: string;
}

export interface Agent {
  agent_id: string;
  pseudonym: string;
  model_id?: string;
  archetype?: string;
  team_id: string;
  status: 'active' | 'eliminated' | 'jury';
  has_immunity: boolean | number;
  confessional_memory: string;
  action_points: number;
  elimination_round?: number | null;
  portrait_seed?: string;
}

export interface Message {
  id: number;
  round?: number;
  turn_index?: number;
  day?: number;
  sender_id: string;
  receiver_ids: string[];
  is_public: boolean;
  inner_thought: string;
  content: string;
  trust_telemetry: Record<string, number>;
  timestamp: string;
}

export interface Vote {
  id?: number;
  round?: number;
  turn_index?: number;
  voter_id: string;
  target_id: string | null;
  target_pseudonym?: string;
  revealed?: boolean | number;
  is_revote?: boolean | number;
}

export interface Turn {
  id: number;
  season_id: number;
  round: number;
  turn_index: number;
  phase: string;
  phase_step: string;
  actor_id: string | null;
  input_summary: string;
  output_summary: string;
  state_delta: Record<string, unknown>;
  status: string;
  created_at: string;
}

export interface StoryEvent {
  id: number;
  turn_id: number;
  round: number;
  sequence: number;
  phase: string;
  kind:
    | 'establishing'
    | 'conversation'
    | 'confessional'
    | 'host_question'
    | 'tribal_answer'
    | 'vote_booth'
    | 'vote_reveal'
    | 'elimination'
    | 'exit_confessional'
    | string;
  scene: 'camp' | 'confessional' | 'tribal' | string;
  shot: string;
  actor_ids: string[];
  target_ids: string[];
  visibility: string;
  title: string;
  dialogue: string;
  subtitle?: string | null;
  inner_thought?: string | null;
  trust_telemetry: Record<string, number>;
  duration_ms: number;
  animation: string;
  spoiler_group?: string | null;
  payload: Record<string, unknown> & { voice_timeline?: VoiceTimelineLine[] };
  created_at: string;
}

export interface VoiceTimelineLine {
  story_event_id: number;
  line_index: number;
  speaker_id: string;
  speaker_label: string;
  text: string;
  audio_url: string | null;
  duration_ms: number;
  start_ms: number;
  end_ms: number;
  status: 'pending' | 'ready' | 'failed' | 'skipped' | string;
}

export interface ApiStateResponse {
  game: GameState;
  agents: Agent[];
  messages: Message[];
  votes: Vote[];
  turn_count: number;
  story_event_count: number;
  llm?: LLMSettings;
  next_round_preload?: NextRoundPreloadStatus | null;
  viewer_state?: ViewerState | null;
}

export interface GameSummary {
  game: GameState;
  winner: Agent | null;
  active_agents: Agent[];
  eliminated_jury: Agent[];
  round_history: Array<{
    round: number;
    event_count: number;
    challenge_result: Record<string, unknown> | null;
    eliminated_id: string | null;
    eliminated_name: string | null;
    votes: Vote[];
  }>;
  challenge_wins: Record<string, number>;
  immunity_wins: Record<string, number>;
  votes_received: Record<string, number>;
  votes: Vote[];
  jury_votes: Array<Record<string, unknown>>;
  finale_status: {
    is_finale: boolean;
    finalists: Agent[];
    jury_count: number;
    remaining_eliminations_to_finale: number;
    winner_declared: boolean;
  };
}

export interface ModelRoster {
  id: string;
  name: string;
  models: Array<{
    model_id: string;
    display_name: string;
    status: string;
  }>;
}

export interface ViewerState {
  season_id: number;
  round: number;
  phase: string;
  replay_index: number;
  is_playing: boolean;
  updated_at: string;
}

export interface LLMSettings {
  provider: 'openrouter';
  openrouter_configured: boolean;
  default_model_id: string;
  timeout_seconds: number;
  site_url: string;
  app_name: string;
}

export interface NextRoundPreloadStatus {
  id: number;
  source_round: number;
  target_round: number;
  phase: string;
  status: 'pending' | 'running' | 'complete' | 'failed' | string;
  provider: 'openrouter' | 'openrouter_failed' | string;
  event_count: number;
  context_digest: Record<string, unknown>;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface EpisodeResponse {
  round: number;
  phase: string;
  title: string;
  runtime_ms: number;
  events: StoryEvent[];
  agents: Agent[];
  game: GameState;
}

export interface ArenaEntry {
  entry_id: string;
  room_id: string;
  seat_no: number;
  participant_type: 'human' | 'cpu';
  wallet_address: string | null;
  payout_address: string | null;
  character_name: string;
  avatar_seed: string;
  model_id: string;
  soul_sha256: string;
  archetype: string;
  status: string;
  payment_id: string | null;
  locked_at: string | null;
  created_at: string;
}

export interface ArenaEconomics {
  human_entry_count: number;
  gross_entry_cents: number;
  human_winner_payout_cents: number;
  cpu_winner_refund_per_human_cents: number;
  house_fee_cents: number;
}

export interface ArenaRoom {
  room_id: string;
  status: 'open' | 'running' | 'completed' | string;
  title: string;
  entry_amount_cents: number;
  currency: string;
  network: string;
  asset_contract: string;
  max_seats: number;
  cpu_fill_enabled: number | boolean;
  locked_human_count: number;
  start_vote_count: number;
  cpu_fill_count: number;
  can_start: boolean;
  entries: ArenaEntry[];
  economics: ArenaEconomics;
}

export interface ArenaBroadcastEvent {
  id: number;
  season_id: string;
  broadcast_seq: number;
  kind: string;
  title: string;
  body: string;
  payload: Record<string, unknown>;
}

export interface ArenaMoneyMovement {
  payout_id?: string;
  refund_id?: string;
  season_id: string;
  entry_id: string;
  amount_cents: number;
  status: string;
  reason: string;
  created_at: string;
}

export interface ArenaSeasonManifest {
  season: {
    season_id: string;
    room_id: string;
    status: string;
    winner_entry_id: string | null;
    winner_participant_type: 'human' | 'cpu' | null;
    created_at: string;
  };
  room: ArenaRoom;
  entries: ArenaEntry[];
  broadcast_events: ArenaBroadcastEvent[];
  payouts: ArenaMoneyMovement[];
  refunds: ArenaMoneyMovement[];
  economics: ArenaEconomics;
}
