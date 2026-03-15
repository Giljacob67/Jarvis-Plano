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
- **Workflow**: `Jarvis Pessoal` — runs `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- **Tests**: `pytest tests/ -v` (21 tests)

### Python project structure

```text
app/
├── main.py              # FastAPI app with lifespan (TelegramService start/stop), error handler
├── config.py            # Pydantic Settings (reads .env, includes openai_model, context limits, tool round limits)
├── db.py                # SQLAlchemy engine, session, Base
├── prompts.py           # System prompt (pt-BR) and context formatting helpers
├── models/              # SQLAlchemy models
│   ├── user.py          # User (telegram_user_id as String PK)
│   ├── processed_update.py  # ProcessedTelegramUpdate (idempotency)
│   ├── conversation.py  # Conversation
│   ├── message.py       # Message (role, text, raw_json)
│   ├── memory_item.py   # MemoryItem (user notes/reminders)
│   └── action_log.py    # ActionLog (sensitive actions blocked)
├── schemas/             # Pydantic schemas (health, telegram, day, common)
├── routes/
│   ├── health.py        # GET /health
│   ├── telegram.py      # POST /webhooks/telegram (secret validation → user filter → idempotency → dispatch)
│   ├── auth.py          # Google OAuth stubs (501)
│   └── day.py           # GET /me/day (mock data)
├── services/
│   ├── telegram.py      # TelegramService (reused httpx.AsyncClient, send_message, set_webhook, etc.)
│   ├── openai_service.py  # OpenAIService (Responses API, function calling, tool round limit)
│   ├── assistant_service.py  # AssistantService (orchestrates context, history, memories, tool execution)
│   ├── memory_service.py    # save_memory, list_memories, search_memories
│   ├── google_calendar.py   # Stub (Fase 3)
│   ├── gmail.py             # Stub (Fase 3)
│   └── google_tasks.py      # Stub (Fase 3)
tests/                   # pytest tests (21 tests: health, auth, day, telegram commands/security/idempotency)
scripts/
├── set_telegram_webhook.py      # Set webhook via Telegram Bot API
└── get_telegram_webhook_info.py # Check current webhook status
requirements.txt         # Python dependencies
.env.example             # Environment variable template
```

### Key env vars (Python)

- `JARVIS_DATABASE_URL` — defaults to `sqlite:///./jarvis.db`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_ALLOWED_USER_ID` (string)
- `OPENAI_API_KEY`, `OPENAI_MODEL` (default: `gpt-5-mini`)
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
- `APP_ENV`, `TIMEZONE`, `APP_BASE_URL`

### Key design decisions

- **user_id as String** everywhere (models, config, comparisons)
- **Single httpx.AsyncClient** in TelegramService (started in lifespan, stopped on shutdown)
- **Tool call round limit** (default 3) to prevent infinite loops in OpenAI function calling
- **Context limits**: configurable max messages (20) and max memories (10) per LLM call
- **All bot responses in pt-BR**
- **Webhook security order**: secret header → allowed user_id → idempotency → dispatch

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
