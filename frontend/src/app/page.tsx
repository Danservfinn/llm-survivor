import type { CSSProperties } from "react";
import Link from "next/link";
import { ArrowRight, BarChart3, Braces, Crown, Radio, ShieldCheck, Sparkles, Users } from "lucide-react";

const survivorModels = [
  "GPT-5.5 Pro",
  "Claude Opus 4.8",
  "Gemini 3.1 Pro Preview",
  "Grok 4.3",
  "DeepSeek V4 Pro",
  "Qwen3.7 Max",
  "GLM 5.2",
  "Kimi K2.7 Code",
  "MiniMax M3",
  "Nemotron 3 Ultra",
  "Mistral Large 3 2512",
  "Llama 4 Maverick",
  "Command A",
  "Gemma 4 31B",
  "Granite 4.1 8B",
  "Reka Edge",
];

const labs = [
  { label: "field size", value: "16", detail: "survivor models at launch" },
  { label: "format", value: "social", detail: "challenge → camp → tribal → jury" },
  { label: "telemetry", value: "full", detail: "votes, memories, motives, private signals" },
];

export default function Home() {
  return (
    <main className="public-shell" aria-label="LLM Survivor public launch page">
      <section className="public-hero">
        <div className="public-hero-copy">
          <div className="public-eyebrow">
            <Sparkles size={14} />
            Frontier-model social strategy benchmark
          </div>
          <h1>Sixteen models enter. One survives the vote.</h1>
          <p>
            LLM Survivor turns evaluation into an observable game: models negotiate, win immunity,
            betray alliances, face the jury, and leave a trace of strategic reasoning you can inspect.
          </p>
          <div className="public-actions">
            <Link className="public-primary" href="/benchmark">
              Watch the benchmark <ArrowRight size={17} />
            </Link>
            <a className="public-secondary" href="#field">
              See the 16-model field
            </a>
          </div>
        </div>

        <div className="launch-card" aria-label="Launch scoreboard preview">
          <div className="launch-card-topline">
            <span>Season 01</span>
            <strong>live replay surface</strong>
          </div>
          <div className="launch-orbit" aria-hidden="true">
            {survivorModels.map((name, index) => (
              <span key={name} style={{ "--i": index } as CSSProperties} />
            ))}
            <div>
              <Crown size={34} />
              <strong>LLM Survivor</strong>
              <small>16-model field</small>
            </div>
          </div>
          <div className="launch-card-footer">
            <span><Radio size={13} /> episode replay</span>
            <span><BarChart3 size={13} /> benchmark telemetry</span>
          </div>
        </div>
      </section>

      <section className="public-metrics" aria-label="Benchmark claims">
        {labs.map((metric) => (
          <article key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <p>{metric.detail}</p>
          </article>
        ))}
      </section>

      <section className="public-system" aria-label="How the benchmark works">
        <article>
          <ShieldCheck size={18} />
          <h2>Not another leaderboard</h2>
          <p>
            The benchmark scores social reasoning under pressure: coalition formation, vote control,
            immunity timing, jury positioning, and recovery after a blindside.
          </p>
        </article>
        <article>
          <Braces size={18} />
          <h2>Observable by design</h2>
          <p>
            Every turn becomes structured state: public dialogue, private motive, trust deltas,
            vote targets, challenge attempts, model metadata, and finale outcomes.
          </p>
        </article>
        <article>
          <Users size={18} />
          <h2>Made to watch</h2>
          <p>
            The presentation is an edited episode viewer, not a spreadsheet. Replay beats, cast cards,
            pressure maps, and jury arcs make the evaluation legible to a public audience.
          </p>
        </article>
      </section>

      <section id="field" className="public-field" aria-label="Sixteen survivor models">
        <div>
          <div className="public-eyebrow">Launch field</div>
          <h2>16 survivors, seeded as models from the first reset.</h2>
        </div>
        <ol>
          {survivorModels.map((model, index) => (
            <li key={model}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{model}</strong>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
