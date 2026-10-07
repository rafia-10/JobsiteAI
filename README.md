# PreCode — Hands-free Site Assistant (Phase 1 PoC)

A working proof of concept for a voice assistant that construction supervisors can talk to
on the way to site. Ask **"what's my priority today and tomorrow"** and get an answer
generated from **real, live project data** in a Postgres database — schedules, trade
allocations, task status, and defects. Not a mockup.

## Quickstart

```bash
cp .env.example .env      # optional: add OPENAI_API_KEY; everything runs without it
docker compose up --build # starts Postgres + FastAPI + React
```

The backend creates its schema and seeds realistic demo data automatically on first start.

- **App:** http://localhost:3000
- **API health (hello world):** http://localhost:8081/api/health
- **Interactive API docs:** http://localhost:8081/docs

> Note: the backend is exposed on host port **8081** (8000 was busy on the dev machine);
> the container itself still listens on 8000. Change the mapping in `docker-compose.yml` if you like.

Seed explicitly (or rebuild the dataset when you change `seed.py`):

```bash
docker compose exec backend python -m app.seed --drop
```

## The 60-second demo

1. Open http://localhost:3000
2. Click **"What's my priority today and tomorrow?"** (or hold the mic and say it)
3. The assistant answers with overdue tasks first, then today's, then tomorrow's —
   each with trade, priority, and open-defect counts pulled from Postgres.
4. Try follow-ups: *"What defects are still open?"*, *"Who's on site this week?"*
5. Prove it's live data: edit a task's due date in the DB (or `POST /api/seed` after
   changing the seeder), ask again, and hear the answer change.

## How it works (architecture)

```
┌──────────┐  Web Speech API / MediaRecorder   ┌─────────────────────┐
│ Browser  │ ──── voice in ───────────────────▶ │ FastAPI  /api/agent │
│  React   │ ◀─── voice out (TTS) ──────────── │        /api/voice   │
└──────────┘                                   └────────┬────────────┘
                                                        │ tool calls (JSON)
                                               ┌────────▼────────────┐
                                               │  queries.py         │  deterministic
                                               │  (SQLAlchemy)       │── SQL-backed tools
                                               └────────┬────────────┘
                                               ┌────────▼────────────┐
                                               │ Postgres            │
                                               └─────────────────────┘
```

**Key design decision:** the LLM never writes SQL and never sees numbers it didn't get
from a tool. It plans and phrases; the database answers. Five deterministic tools
(`get_priority_tasks`, `get_project_status`, `get_defects`, `get_trades_workload`,
`get_tasks`) are the *only* path to data, for both the REST API and the agent. Every
tool call is recorded — `POST /api/agent/debug` shows exactly which queries produced an
answer. This grounding is enforced by the test suite (see *Tests & CI*).

**Interactive, not canned:** answers are LLM-generated (Groq `openai/gpt-oss-120b` by
default; any OpenAI-compatible endpoint works) and streamed token-by-token over SSE
(`POST /api/agent/stream`). The agent keeps **conversation memory** — follow-ups like
*"and which task is the critical one on?"* resolve against earlier turns. The UI shows
live tool activity ("checking today's schedule…"), a typing caret, and contextual
follow-up suggestions derived from what the tools just returned. If no API key is set,
a deterministic fallback keeps the demo alive; it too resolves simple follow-ups from
history.

**Voice:**
- *Input:* browser Web Speech API (Chrome/Edge, zero keys) with automatic fallback to
  `MediaRecorder → POST /api/voice/transcribe` (Groq Whisper server-side).
- *Output:* server TTS at `POST /api/voice/speak` (Groq Orpheus) when available, with
  automatic per-session fallback to browser speech synthesis. Sentences are spoken as
  they stream in, not after the full answer.

**No API key? Still works.** A deterministic fallback answers the core questions
(priority today/tomorrow, defects, crews, project status) from the same query layer, so
the demo never depends on an external service. Set `OPENAI_API_KEY` to switch to full
LLM tool-calling. Any OpenAI-compatible endpoint works (OpenAI, OpenRouter, local
vLLM/ollama via `LLM_BASE_URL`).

## Schema (designed up front)

```
supervisors 1──* projects 1──* tasks *──1 trades
                   │             │
                   │             └──* defects
                   └──* trade_assignments *──1 trades
```

| table | purpose |
|---|---|
| `supervisors` | platform users who run builds |
| `projects` | a residential build; owner supervisor, status, target date |
| `trades` | trade catalogue (Electrician, Plumber, …) |
| `trade_assignments` | crew of a trade allocated to a project (lead, size, dates) |
| `tasks` | unit of work: project + trade + status + priority + scheduled/due dates |
| `defects` | issue raised against a task, with severity and status |

Seed data (dates generated **relative to today**, so the demo always looks live):
8 supervisors, 8 projects across all four statuses (4 active, 2 completed, 1 planning,
1 paused), 13 trades, 47 crew allocations, 114 tasks spanning overdue / today /
tomorrow / this week / next week / completed / blocked, and 38 defects covering
every severity and status. The flagship demo build ("14 Kowhai Crescent") keeps an
exact 21-task programme with 6 active defects — the test suite pins those numbers.

## API surface

| endpoint | purpose |
|---|---|
| `GET /api/health` | hello-world: API + DB round-trip |
| `GET /api/priority` | today / tomorrow / overdue buckets + summary |
| `GET /api/tasks?status=&trade=&on_date=` | filtered task list |
| `GET /api/defects?status=` | defect list |
| `GET /api/projects` / `GET /api/trades` / `GET /api/trade-assignments` | reference data |
| `POST /api/agent/ask` | `{question, history}` → grounded answer + citations + suggested follow-ups |
| `POST /api/agent/stream` | same, as SSE: `tool` / `tool_result` / `delta` / `sentence` / `done` events |
| `POST /api/agent/debug` | same + raw tool calls and data snapshot |
| `POST /api/voice/transcribe` | multipart audio → transcript (needs API key) |
| `POST /api/voice/speak` | text → MP3 stream (needs API key) |
| `POST /api/seed?drop=true` | re-seed dataset |

## Tests & CI

The agent's grounding is enforced by a test suite (`backend/tests/`, 33 tests):

- **`test_queries.py`** — every query-layer tool returns data consistent with the seed (priority buckets, filters, defect counts, crew workload).
- **`test_agent.py`** — deterministic fallback answers must cite real seed entities; the LLM tool-calling loop is tested with a **mocked OpenAI client**, asserting that tool results are recorded as structured data and that LLM failures degrade to the fallback instead of erroring.
- **`test_api.py`** — end-to-end route tests over an isolated in-memory SQLite database (health, priority, filtered lists, agent ask/debug with citations, validation).

Run locally:

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -q          # no DB or API key needed — runs on in-memory SQLite
```

GitHub Actions (`.github/workflows/ci.yml`) runs the backend tests and the frontend production build on every push/PR.

## Deploying to Render

The repo ships a [Render Blueprint](https://render.com/docs/blueprint-spec) (`render.yaml` at
the repo root) that defines the whole stack — push the repo to GitHub, then:

**Render Dashboard → New → Blueprint → select the repo**

It provisions three resources (region `singapore`, free tier):

| resource | what it is |
|---|---|
| `precode-api` | FastAPI backend (Docker, `backend/`), health check `/api/health` |
| `precode-web` | React UI + nginx `/api` proxy (Docker, `frontend/`) |
| `precode-db` | Render Postgres, injected into the API as `DATABASE_URL` |

Notes:

- The Blueprint wires `BACKEND_URL` (the API's public URL) into the frontend
  automatically, so the deployed app is same-origin — no CORS, SSE streaming works
  as-is. Both containers bind `$PORT`, which Render sets to `10000`.
- The API creates its schema and seeds demo data on first start, same as local.
- `OPENAI_API_KEY` is left unset on purpose (`sync: false`). Without it the agent
  uses the deterministic fallback and the demo still works; set it (plus the
  `LLM_*` / `STT_*` / `TTS_*` values from `.env.example`) in the dashboard for
  LLM-powered answers and server-side voice.
- Free-tier services spin down after ~15 min idle: the first request after that
  takes ~30 s to wake up. Bump `plan` in `render.yaml` to keep them always-on.

App: `https://precode-web.onrender.com` · API docs: `https://precode-api.onrender.com/docs`

## Running without Docker (dev)

```bash
# backend
cd backend && pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://precode:precode_dev@localhost:5433/precode
uvicorn app.main:app --reload

# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173, proxies /api to :8000
```

## Deliberate Phase-1 simplifications

- One supervisor / one project is surfaced (the brief's PoC scope); schema already
  supports many.
- "Supervisor context" is implicit (first ACTIVE project), not auth-scoped yet.
- Voice activity detection is push-to-talk (correct for driving); continuous wake-word
  listening is a Phase-2 item.
- CORS is open in dev; lock down behind auth before anything real.
