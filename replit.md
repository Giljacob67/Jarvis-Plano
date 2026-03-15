# Workspace

## Overview

Hybrid workspace: a pnpm monorepo (TypeScript) plus a standalone Python FastAPI project ("Jarvis Pessoal").

## Jarvis Pessoal (Python API)

- **Framework**: FastAPI 0.135+
- **Python version**: 3.12
- **Package manager**: pip + requirements.txt
- **Database**: SQLAlchemy with SQLite (configurable via `JARVIS_DATABASE_URL`)
- **AI**: OpenAI Responses API with function calling (model default: `gpt-5-mini`)
- **Bot**: Telegram Bot API via webhooks
- **Google**: OAuth 2.0 + Calendar API + Tasks API + Gmail API (real data when connected, mock fallback)
- **Workflow**: `Jarvis Pessoal` — runs `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- **Voice**: OpenAI Audio API (transcribe + TTS), Telegram voice/audio download and send
- **Tests**: `pytest tests/ -v` (114 tests)

### Python project structure

```text
app/
├── main.py              # FastAPI app with lifespan (TelegramService start/stop), error handler
├── config.py            # Pydantic Settings (reads .env, includes Google OAuth scopes, encryption key)
├── db.py                # SQLAlchemy engine, session, Base
├── prompts.py           # System prompt (pt-BR) and context formatting helpers
├── models/              # SQLAlchemy models
│   ├── user.py          # User (telegram_user_id as String PK)
│   ├── processed_update.py  # ProcessedTelegramUpdate (idempotency)
│   ├── conversation.py  # Conversation
│   ├── message.py       # Message (role, text, raw_json)
│   ├── memory_item.py   # MemoryItem (user notes/reminders)
│   ├── action_log.py    # ActionLog (sensitive actions blocked)
│   ├── google_credential.py  # GoogleCredential (OAuth tokens per user)
│   └── voice_message_log.py  # VoiceMessageLog (voice processing metadata, transcription_raw_json)
├── schemas/             # Pydantic schemas (health, telegram, day, common)
├── routes/
│   ├── health.py        # GET /health
│   ├── telegram.py      # POST /webhooks/telegram (commands + voice/audio pipeline)
│   ├── auth.py          # Google OAuth routes (/start, /callback, /status, /disconnect)
│   └── day.py           # GET /me/day (real data or mock fallback)
├── services/
│   ├── telegram.py      # TelegramService (download_file, send_voice, send_audio)
│   ├── audio_service.py   # AudioService (transcribe, TTS, voice preference)
│   ├── openai_service.py  # OpenAIService (Responses API, function calling, 16 tools)
│   ├── assistant_service.py  # Orchestrates context, history, memories, tool execution, Google/Gmail fallback
│   ├── memory_service.py    # save_memory, list_memories, search_memories
│   ├── google_oauth_service.py  # OAuth flow (auth URL, code exchange, token refresh, revoke, has_gmail_scopes)
│   ├── google_calendar.py   # Google Calendar API (list events, create events)
│   ├── google_tasks.py      # Google Tasks API (list tasks, create tasks, complete tasks)
│   ├── google_gmail_service.py  # Gmail API (list, get, thread, drafts, send, reply)
│   └── gmail.py             # Deprecated stub (kept for compatibility)
├── utils/
│   ├── date_utils.py    # Timezone helpers (today_bounds, parse_datetime, week_bounds)
│   └── gmail_utils.py   # Gmail helpers (MIME, headers, body extraction, formatting)
tests/                   # pytest tests (87 tests)
scripts/
├── set_telegram_webhook.py
└── get_telegram_webhook_info.py
requirements.txt
.env.example
```

### Key env vars (Python)

- `JARVIS_DATABASE_URL` — defaults to `sqlite:///./jarvis.db`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_ALLOWED_USER_ID` (string)
- `OPENAI_API_KEY`, `OPENAI_MODEL` (default: `gpt-5-mini`)
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
- `GOOGLE_OAUTH_SCOPES` — defaults to `calendar.events tasks`
- `GOOGLE_GMAIL_ENABLED` — `true` (default) or `false`
- `GOOGLE_GMAIL_SCOPES` — defaults to `gmail.readonly gmail.compose`
- `GMAIL_INBOX_QUERY_DEFAULT`, `GMAIL_MAX_LIST_RESULTS`
- `OPENAI_TRANSCRIBE_MODEL` — default `gpt-4o-mini-transcribe`
- `OPENAI_TTS_MODEL` — default `gpt-4o-mini-tts`
- `VOICE_RESPONSES_ENABLED` — `false` (default); set `true` to enable TTS replies
- `VOICE_RESPONSE_VOICE` — TTS voice (default: `alloy`)
- `MAX_AUDIO_FILE_MB` — max audio size (default: `19`, max: `20`)
- `TEMP_AUDIO_DIR` — temp dir for audio files (default: `/tmp/jarvis_audio`)
- `GOOGLE_ENCRYPTION_KEY` — reserved for future token encryption
- `APP_ENV`, `TIMEZONE`, `APP_BASE_URL`

### Key design decisions

- **user_id as String** everywhere (models, config, comparisons)
- **Single httpx.AsyncClient** in TelegramService (started in lifespan, stopped on shutdown)
- **Tool call round limit** (default 3) to prevent infinite loops in OpenAI function calling
- **Context limits**: configurable max messages (20) and max memories (10) per LLM call
- **All bot responses in pt-BR**
- **Webhook security order**: secret header → allowed user_id → idempotency → dispatch
- **Google OAuth**: access_type=offline, prompt=consent, state validation (CSRF protection)
- **Google fallback**: When not connected, /myday and /me/day return mock data
- **Tokens stored as plain text** for now (GOOGLE_ENCRYPTION_KEY reserved for future)
- **OAuth state**: stored in-memory dict (_pending_states); cleared on use

## Node.js / TypeScript Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Structure

```text
artifacts-monorepo/
├── artifacts/              # Deployable applications
│   └── api-server/         # Express API server
├── lib/                    # Shared libraries
│   ├── api-spec/           # OpenAPI spec + Orval codegen config
│   ├── api-client-react/   # Generated React Query hooks
│   ├── api-zod/            # Generated Zod schemas from OpenAPI
│   └── db/                 # Drizzle ORM schema + DB connection
├── scripts/                # Utility scripts (single workspace package)
│   └── src/                # Individual .ts scripts, run via `pnpm --filter @workspace/scripts run <script>`
├── pnpm-workspace.yaml     # pnpm workspace (artifacts/*, lib/*, lib/integrations/*, scripts)
├── tsconfig.base.json      # Shared TS options (composite, bundler resolution, es2022)
├── tsconfig.json           # Root TS project references
└── package.json            # Root package with hoisted devDeps
```

## TypeScript & Composite Projects

Every package extends `tsconfig.base.json` which sets `composite: true`. The root `tsconfig.json` lists all packages as project references. This means:

- **Always typecheck from the root** — run `pnpm run typecheck` (which runs `tsc --build --emitDeclarationOnly`). This builds the full dependency graph so that cross-package imports resolve correctly. Running `tsc` inside a single package will fail if its dependencies haven't been built yet.
- **`emitDeclarationOnly`** — we only emit `.d.ts` files during typecheck; actual JS bundling is handled by esbuild/tsx/vite...etc, not `tsc`.
- **Project references** — when package A depends on package B, A's `tsconfig.json` must list B in its `references` array. `tsc --build` uses this to determine build order and skip up-to-date packages.

## Root Scripts

- `pnpm run build` — runs `typecheck` first, then recursively runs `build` in all packages that define it
- `pnpm run typecheck` — runs `tsc --build --emitDeclarationOnly` using project references

## Packages

### `artifacts/api-server` (`@workspace/api-server`)

Express 5 API server. Routes live in `src/routes/` and use `@workspace/api-zod` for request and response validation and `@workspace/db` for persistence.

- Entry: `src/index.ts` — reads `PORT`, starts Express
- App setup: `src/app.ts` — mounts CORS, JSON/urlencoded parsing, routes at `/api`
- Routes: `src/routes/index.ts` mounts sub-routers; `src/routes/health.ts` exposes `GET /health` (full path: `/api/health`)
- Depends on: `@workspace/db`, `@workspace/api-zod`
- `pnpm --filter @workspace/api-server run dev` — run the dev server
- `pnpm --filter @workspace/api-server run build` — production esbuild bundle (`dist/index.cjs`)
- Build bundles an allowlist of deps (express, cors, pg, drizzle-orm, zod, etc.) and externalizes the rest

### `lib/db` (`@workspace/db`)

Database layer using Drizzle ORM with PostgreSQL. Exports a Drizzle client instance and schema models.

- `src/index.ts` — creates a `Pool` + Drizzle instance, exports schema
- `src/schema/index.ts` — barrel re-export of all models
- `src/schema/<modelname>.ts` — table definitions with `drizzle-zod` insert schemas (no models definitions exist right now)
- `drizzle.config.ts` — Drizzle Kit config (requires `DATABASE_URL`, automatically provided by Replit)
- Exports: `.` (pool, db, schema), `./schema` (schema only)

Production migrations are handled by Replit when publishing. In development, we just use `pnpm --filter @workspace/db run push`, and we fallback to `pnpm --filter @workspace/db run push-force`.

### `lib/api-spec` (`@workspace/api-spec`)

Owns the OpenAPI 3.1 spec (`openapi.yaml`) and the Orval config (`orval.config.ts`). Running codegen produces output into two sibling packages:

1. `lib/api-client-react/src/generated/` — React Query hooks + fetch client
2. `lib/api-zod/src/generated/` — Zod schemas

Run codegen: `pnpm --filter @workspace/api-spec run codegen`

### `lib/api-zod` (`@workspace/api-zod`)

Generated Zod schemas from the OpenAPI spec (e.g. `HealthCheckResponse`). Used by `api-server` for response validation.

### `lib/api-client-react` (`@workspace/api-client-react`)

Generated React Query hooks and fetch client from the OpenAPI spec (e.g. `useHealthCheck`, `healthCheck`).

### `scripts` (`@workspace/scripts`)

Utility scripts package. Each script is a `.ts` file in `src/` with a corresponding npm script in `package.json`. Run scripts via `pnpm --filter @workspace/scripts run <script>`. Scripts can import any workspace package (e.g., `@workspace/db`) by adding it as a dependency in `scripts/package.json`.
