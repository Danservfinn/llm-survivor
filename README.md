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

If port 3000 is already occupied, run `npm run dev -- --port 3001` and open:

- `http://localhost:3001/benchmark`
- `http://localhost:3001/arena`

## APIs

- `GET /api/state`
- `GET /api/episode/current?round=7&phase=tribal`
- `GET /api/episode/current?round=7&phase=tribal&include_audio=true`
- `GET /api/story-events?round=7&from_sequence=0`
- `GET /api/llm/settings`
- `POST /api/llm/settings` with `{ "provider": "simulated" }` or `{ "provider": "openrouter" }`
- `POST /api/turns/advance`
- `POST /api/turns/auto-run` with `{ "max_turns": 25 }`
- `POST /api/voice/build-episode?round=7&phase=tribal`
- `GET /api/voice/status?round=7&phase=tribal`

## LLM Provider Toggle

Benchmarking defaults to simulated calls, which use deterministic fixtures and never contact paid model APIs.

```bash
export LLM_PROVIDER=simulated
```

To allow real model turns, load an OpenRouter key only in the backend shell and switch the Benchmarking header toggle to `Real OpenRouter`:

```bash
export OPENROUTER_API_KEY='...'
export LLM_PROVIDER=openrouter
python3 -m uvicorn backend.api:app --reload --port 8000
```

The toggle affects future turns only. Replaying existing `StoryEvents` never calls models. If `Real OpenRouter` is selected without `OPENROUTER_API_KEY`, the UI shows `Needs key` and the backend uses simulated fallbacks.

Do not put `OPENROUTER_API_KEY` in repo files, wiki pages, frontend code, API payloads, logs, or generated artifacts.

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
