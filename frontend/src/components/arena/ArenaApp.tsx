"use client";

import {
  Bot,
  CheckCircle2,
  Coins,
  Cpu,
  Play,
  ReceiptText,
  RefreshCcw,
  ShieldCheck,
  UserRound,
  Vote,
  Wallet,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { apiUrl } from "@/lib/api";
import type { ArenaEntry, ArenaRoom, ArenaSeasonManifest } from "@/types";

const ROOM_ID = "room-demo";
const DEMO_WALLET = "0xabc12345";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || response.statusText);
  }
  return response.json() as Promise<T>;
}

function money(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

export function ArenaApp() {
  const [room, setRoom] = useState<ArenaRoom | null>(null);
  const [manifest, setManifest] = useState<ArenaSeasonManifest | null>(null);
  const [selectedWinner, setSelectedWinner] = useState<string>("");
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const roomData = await fetchJson<ArenaRoom>(`/api/arena/rooms/${ROOM_ID}`);
    setRoom(roomData);
    return roomData;
  }, []);

  useEffect(() => {
    refresh().catch((refreshError: Error) => setError(refreshError.message));
  }, [refresh]);

  const humanEntries = useMemo(
    () => (room?.entries ?? []).filter((entry) => entry.participant_type === "human"),
    [room?.entries],
  );

  async function run(action: () => Promise<void>) {
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

  const lockDemoHuman = () =>
    run(async () => {
      await fetchJson(`/api/arena/rooms/${ROOM_ID}/entry`, {
        method: "POST",
        body: JSON.stringify({
          wallet_address: DEMO_WALLET,
          character_name: "Human Prime",
          model_id: "openai/gpt-4.1",
          soul_md: "# Human Prime\n\nWin by building calm trust, tracking debts, and cutting threats at six.",
        }),
      });
      await refresh();
    });

  const voteStart = () =>
    run(async () => {
      await fetchJson(`/api/arena/rooms/${ROOM_ID}/start-vote`, {
        method: "POST",
        body: JSON.stringify({ wallet_address: DEMO_WALLET }),
      });
      await refresh();
    });

  const startRoom = () =>
    run(async () => {
      const started = await fetchJson<ArenaSeasonManifest>(`/api/arena/rooms/${ROOM_ID}/start`, {
        method: "POST",
      });
      setManifest(started);
      setSelectedWinner(started.entries.find((entry) => entry.participant_type === "cpu")?.entry_id ?? started.entries[0]?.entry_id ?? "");
      await refresh();
    });

  const resolveSeason = (winnerId: string) =>
    run(async () => {
      if (!manifest) return;
      const resolved = await fetchJson<ArenaSeasonManifest>(`/api/arena/seasons/${manifest.season.season_id}/resolve`, {
        method: "POST",
        body: JSON.stringify({ winner_entry_id: winnerId || null }),
      });
      setManifest(resolved);
      await refresh();
    });

  const resetArena = () =>
    run(async () => {
      await fetchJson("/api/arena/dev/reset", { method: "POST" });
      setManifest(null);
      setSelectedWinner("");
      await refresh();
    });

  const entries = manifest?.entries ?? room?.entries ?? [];
  const economics = manifest?.economics ?? room?.economics;
  const canStart = Boolean(room?.can_start);

  return (
    <main className="arena-shell">
      <section className="arena-hero">
        <div>
          <div className="eyebrow">
            <ShieldCheck size={14} />
            Closed Paid Beta
          </div>
          <h1>Social Strategy Elimination Arena</h1>
          <p>
            Humans pay and lock a character. Empty seats fill with CPU players using curated models
            and default soul profiles. Humans can start as soon as all locked humans vote.
          </p>
        </div>
        <div className="arena-economics-card">
          <span>Base USDC via x402</span>
          <strong>{room ? money(room.entry_amount_cents) : "$25.00"}</strong>
          <p>CPU win refunds 90% of each human entry; house keeps 10%.</p>
        </div>
      </section>

      {error && <div className="arena-error" role="alert">{error}</div>}

      <section className="arena-grid">
        <div className="arena-panel arena-control-panel">
          <header>
            <h2>Room Control</h2>
            <span>{room?.status ?? "loading"}</span>
          </header>

          <div className="arena-metrics">
            <Metric icon={<UserRound size={18} />} label="Humans" value={`${room?.locked_human_count ?? 0}`} />
            <Metric icon={<Cpu size={18} />} label="CPU Fill" value={`${room?.cpu_fill_count ?? 0}`} />
            <Metric icon={<Vote size={18} />} label="Start Votes" value={`${room?.start_vote_count ?? 0}/${room?.locked_human_count ?? 0}`} />
            <Metric icon={<Coins size={18} />} label="Human Pool" value={economics ? money(economics.gross_entry_cents) : "$0.00"} />
          </div>

          <div className="arena-actions">
            <button type="button" onClick={lockDemoHuman} disabled={isBusy || room?.status !== "open"}>
              <Wallet size={16} />
              Lock Demo Human
            </button>
            <button type="button" onClick={voteStart} disabled={isBusy || humanEntries.length === 0 || room?.status !== "open"}>
              <Vote size={16} />
              Vote Start
            </button>
            <button type="button" className="primary" onClick={startRoom} disabled={isBusy || room?.status !== "open" || !canStart}>
              <Play size={16} />
              Fill CPU + Start
            </button>
            <button type="button" onClick={resetArena} disabled={isBusy}>
              <RefreshCcw size={16} />
              Reset Arena
            </button>
          </div>

          <div className="arena-rule-callout">
            <strong>Start rule</strong>
            <p>One locked human can start solo. Multiple locked humans must all vote start. CPU players never vote to start.</p>
          </div>
        </div>

        <div className="arena-panel">
          <header>
            <h2>Cast Manifest</h2>
            <span>{entries.length || room?.max_seats || 16} seats</span>
          </header>
          <div className="seat-list">
            {entries.length === 0 && <EmptySeatPreview cpuCount={room?.cpu_fill_count ?? 0} />}
            {entries.map((entry) => (
              <SeatCard key={entry.entry_id} entry={entry} />
            ))}
          </div>
        </div>
      </section>

      <section className="arena-grid lower">
        <div className="arena-panel">
          <header>
            <h2>Broadcast</h2>
            <span>{manifest?.season.status ?? "not started"}</span>
          </header>
          <div className="broadcast-event-list">
            {(manifest?.broadcast_events ?? []).map((event) => (
              <article key={event.id}>
                <span>{String(event.broadcast_seq).padStart(2, "0")}</span>
                <div>
                  <strong>{event.title}</strong>
                  <p>{event.body}</p>
                </div>
              </article>
            ))}
            {!manifest && <p className="muted-copy">Start the room to commit the cast manifest and broadcast cursor.</p>}
          </div>
        </div>

        <div className="arena-panel">
          <header>
            <h2>Result Simulation</h2>
            <span>paid beta economics</span>
          </header>
          <div className="result-tools">
            <select value={selectedWinner} onChange={(event) => setSelectedWinner(event.target.value)} disabled={!manifest || isBusy}>
              <option value="">Choose winner</option>
              {(manifest?.entries ?? []).map((entry) => (
                <option key={entry.entry_id} value={entry.entry_id}>
                  {entry.character_name} ({entry.participant_type})
                </option>
              ))}
            </select>
            <button
              type="button"
              className="primary"
              onClick={() => resolveSeason(selectedWinner)}
              disabled={!manifest || manifest.season.status === "completed" || !selectedWinner || isBusy}
            >
              <ReceiptText size={16} />
              Resolve Season
            </button>
          </div>

          <MoneyMovements manifest={manifest} />
        </div>
      </section>
    </main>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="arena-metric">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EmptySeatPreview({ cpuCount }: { cpuCount: number }) {
  return (
    <article className="seat-card cpu">
      <Bot size={18} />
      <div>
        <strong>{cpuCount || 16} CPU seats ready</strong>
        <p>Curated model cast with default soul profiles fills empty seats at start.</p>
      </div>
    </article>
  );
}

function SeatCard({ entry }: { entry: ArenaEntry }) {
  return (
    <article className={`seat-card ${entry.participant_type}`}>
      {entry.participant_type === "cpu" ? <Bot size={18} /> : <UserRound size={18} />}
      <div>
        <strong>
          {String(entry.seat_no).padStart(2, "0")} | {entry.character_name}
        </strong>
        <p>{entry.model_id}</p>
        <small>
          {entry.participant_type.toUpperCase()} | {entry.archetype} | soul {entry.soul_sha256.slice(0, 8)}
        </small>
      </div>
      {entry.status === "locked" && <CheckCircle2 size={18} />}
    </article>
  );
}

function MoneyMovements({ manifest }: { manifest: ArenaSeasonManifest | null }) {
  if (!manifest) {
    return <p className="muted-copy">Resolve a started season to create payout or refund records.</p>;
  }
  if (manifest.payouts.length === 0 && manifest.refunds.length === 0) {
    return <p className="muted-copy">No winner declared yet.</p>;
  }
  return (
    <div className="money-list">
      {manifest.payouts.map((payout) => (
        <article key={payout.payout_id}>
          <strong>Winner payout queued</strong>
          <span>{money(payout.amount_cents)}</span>
          <p>{payout.reason}</p>
        </article>
      ))}
      {manifest.refunds.map((refund) => (
        <article key={refund.refund_id}>
          <strong>CPU-win refund queued</strong>
          <span>{money(refund.amount_cents)}</span>
          <p>{refund.reason}</p>
        </article>
      ))}
    </div>
  );
}
