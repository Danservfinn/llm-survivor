# LLM Survivor

LLM Survivor is a turn-based social strategy simulation with a TV-style episode replay viewer.

The current workspace has two local frontends:

- `/benchmark` — deterministic LLM benchmarking/operator replay.
- `/arena` — closed paid-beta arena flow with human entries, CPU fill seats, start votes, and payout/refund simulation.

The benchmark MVP is a deterministic Tribal Conference episode:

- camp strategy conversations
- one-on-one confessionals
- host questions
- vote-booth moments
- vote-card reveal
- elimination
- exit confessional

The backend stores canonical state changes in `Turns` and stable presentation beats in `StoryEvents`. The frontend plays those events like an edited episode and never advances game state except by calling the turn API.

## Run Locally

From `/Users/kurultai/llm-survivor`:

```bash
python3 -m uvicorn backend.api:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open `http://localhost:3000`.

If the backend is on a non-default port, point the frontend at it:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8001 npm run dev -- --port 3000
```

If port 3000 is already occupied, run `npm run dev -- --port 3001` and open:

- `http://localhost:3001/benchmark`
- `http://localhost:3001/arena`

## APIs

- `GET /api/state`
- `GET /api/episode/current?round=7&phase=tribal`
- `GET /api/episode/current?round=7&phase=tribal&include_audio=true`
- `GET /api/story-events?round=7&from_sequence=0`
- `GET /api/llm/settings`
- `POST /api/llm/settings` with `{ "provider": "openrouter" }` or `{ "provider": "ollama" }`
- `POST /api/turns/advance`
- `POST /api/turns/auto-run` with `{ "max_turns": 25 }`
- `POST /api/voice/build-episode?round=7&phase=tribal`
- `GET /api/voice/status?round=7&phase=tribal`

## LLM Provider Toggle

Benchmarking defaults to deterministic fallbacks unless a live provider is configured. Replaying existing `StoryEvents` never calls models.

```bash
export LLM_PROVIDER=openrouter
```

To allow OpenRouter turns, load an OpenRouter key only in the backend shell and switch the Benchmarking header provider to `OpenRouter`:

```bash
export OPENROUTER_API_KEY='...'
export LLM_PROVIDER=openrouter
python3 -m uvicorn backend.api:app --reload --port 8000
```

If `OpenRouter` is selected without `OPENROUTER_API_KEY`, the UI shows `Needs key` and the backend uses deterministic fallbacks.

Do not put `OPENROUTER_API_KEY` in repo files, wiki pages, frontend code, API payloads, logs, or generated artifacts.

### Local Ollama on Kublai

The Benchmark provider selector also supports an all-local Ollama configuration. Start Ollama on the same host as the backend, or forward Kublai's local Ollama port before starting the backend:

```bash
ssh -N -L 11434:127.0.0.1:11434 kublai@100.69.84.64
```

Then run:

```bash
export LLM_PROVIDER=ollama
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export OLLAMA_HOST_MODEL=qwen3.5:9b
export OLLAMA_KEEP_ALIVE_PER_CALL=0
export OLLAMA_NUM_CTX=8192
export OLLAMA_TIMEOUT_SECONDS=180
python3 -m uvicorn backend.api:app --reload --port 8000
```

Select `Local Ollama` in the frontend provider dropdown, then select `All Local Ollama Models` or reset with the local roster. The local roster starts at round 7 and uses `qwen3.5:9b`, `qwen3.5:4b`, `gemma3:4b`, `llama3.2:3b`, `phi4-mini`, and `deepseek-r1:7b`.

## ElevenLabs Voice

Voice generation is explicit and server-side. The frontend never calls ElevenLabs directly.

Local/test runs default to the fake provider and do not need a secret:

```bash
export VOICE_PROVIDER=fake
python3 -m uvicorn backend.api:app --reload --port 8000
```

For real ElevenLabs generation, rotate any key that was pasted into chat first, then load the new key only in the backend shell:

```bash
export ELEVENLABS_API_KEY='...'
export VOICE_PROVIDER=elevenlabs
python3 -m uvicorn backend.api:app --reload --port 8000
```

Do not put `ELEVENLABS_API_KEY` in repo files, wiki pages, frontend code, API payloads, logs, or generated artifacts.

Arena APIs:

- `GET /api/arena/rooms`
- `GET /api/arena/rooms/{room_id}`
- `POST /api/arena/rooms/{room_id}/entry`
- `POST /api/arena/rooms/{room_id}/start-vote`
- `POST /api/arena/rooms/{room_id}/start`
- `GET /api/arena/seasons/{season_id}/manifest`
- `GET /api/arena/seasons/{season_id}/broadcast-events`
- `POST /api/arena/seasons/{season_id}/resolve`

For local development only:

- `POST /api/dev/reset`
- `POST /api/arena/dev/reset`

## Test

```bash
python3 -m unittest discover -s backend/tests -v
```
