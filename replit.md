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
- **Proactive**: Scheduler with morning briefing, evening review, due task/event reminders
- **Approvals**: Pending approval center for sensitive actions (email send, follow-up, event creation)
- **Workflows**: 7 playbooks (lead_followup, meeting_prep, inbox_triage + 4 browser playbooks)
- **Browser Automation**: Playwright Chromium, domain allowlist, approval-gated sensitive actions, login detection, screenshot, download, text extraction
- **Tests**: run per-file with `pytest tests/<file>.py -v` (227+ tests across 11 files; running all at once may cause asyncio teardown warnings)

### Python project structure

```text
app/
├── main.py              # FastAPI app with lifespan (TelegramService, scheduler start/stop), error handler
├── config.py            # Pydantic Settings (reads .env, includes Google OAuth scopes, encryption key, Phase 6 config)
├── db.py                # SQLAlchemy engine, session, Base
├── prompts.py           # System prompt (pt-BR) and context formatting helpers
├── models/              # SQLAlchemy models
│   ├── user.py          # User (telegram_user_id as String PK)
│   ├── processed_update.py  # ProcessedTelegramUpdate (idempotency)
│   ├── conversation.py  # Conversation
│   ├── message.py       # Message (role, text, raw_json)
│   ├── memory_item.py   # MemoryItem (user notes/reminders with categories)
│   ├── action_log.py    # ActionLog (all events: suggestions, approvals, proactive msgs)
│   ├── google_credential.py  # GoogleCredential (OAuth tokens per user)
│   ├── voice_message_log.py  # VoiceMessageLog (voice processing metadata)
│   ├── routine_config.py     # RoutineConfig (per-user routine on/off)
│   ├── pending_approval.py   # PendingApproval (approval center with expiry + idempotency)
│   ├── workflow_run.py       # WorkflowRun (playbook execution log)
│   ├── suggestion_log.py     # SuggestionLog (proactive suggestion tracking)
│   ├── routine_execution_log.py  # RoutineExecutionLog (dedup for scheduler runs)
│   ├── browser_session.py    # BrowserSession (Playwright session per user, TTL, status)
│   ├── browser_step_log.py   # BrowserStepLog (per-action log with screenshot path)
│   └── browser_artifact.py   # BrowserArtifact (screenshots + downloads metadata)
├── schemas/             # Pydantic schemas (health, telegram, day, common)
├── routes/
│   ├── health.py        # GET /health
│   ├── telegram.py      # POST /webhooks/telegram (all commands + voice/audio pipeline)
│   ├── auth.py          # Google OAuth routes (/start, /callback, /status, /disconnect)
│   └── day.py           # GET /me/day (real data or mock fallback)
├── services/
│   ├── telegram.py      # TelegramService (download_file, send_voice, send_audio)
│   ├── audio_service.py   # AudioService (transcribe, TTS, voice preference)
│   ├── openai_service.py  # OpenAIService (Responses API, function calling, 23 tools)
│   ├── assistant_service.py  # Orchestrates context, history, memories, tool execution
│   ├── memory_service.py    # save_memory, list_memories, search_memories, get_memories_by_context
│   ├── google_oauth_service.py  # OAuth flow (auth URL, code exchange, token refresh, revoke)
│   ├── google_calendar.py   # Google Calendar API (list events, create events)
│   ├── google_tasks.py      # Google Tasks API (list tasks, create tasks, complete tasks)
│   ├── google_gmail_service.py  # Gmail API (list, get, thread, drafts, send, reply)
│   ├── approval_service.py     # Approval center (create, list, approve, reject, execute; browser types added)
│   ├── proactive_service.py    # Proactive features (briefing, review, suggestions, quiet hours)
│   ├── workflow_service.py     # Workflow/playbook engine (7 playbooks: 3 existing + 4 browser)
│   ├── scheduler_service.py    # Asyncio scheduler (routines, reminders, hourly browser cleanup)
│   ├── browser_service.py      # Playwright browser automation (shared _browser + per-session context)
│   └── gmail.py             # Deprecated stub
├── utils/
│   ├── date_utils.py    # Timezone helpers
│   ├── gmail_utils.py   # Gmail helpers
│   └── browser_utils.py # Domain allowlist, sensitive action heuristics, login page detection, text summary
tests/                   # pytest tests (227+ across 11 files)
scripts/
├── set_telegram_webhook.py
└── get_telegram_webhook_info.py
requirements.txt
.env.example
```

### Telegram commands

| Command | Description |
|---------|-------------|
| /start, /help | Welcome / help text |
| /myday | Full day overview (agenda + tasks + emails + approvals + suggestions) |
| /briefing | Morning briefing |
| /review | Evening review / day closing |
| /remember <text> | Save a note |
| /memories | List recent notes |
| /connectgoogle | Connect Google account |
| /google | Google connection status |
| /tasks | List pending tasks |
| /newtask <title> | Create task |
| /newevent <title>\|<start>\|<end> | Create calendar event |
| /inbox | Recent inbox emails |
| /emailsearch <query> | Search emails |
| /thread <id> | View email thread |
| /draftemail <to>\|<subject>\|<body> | Create draft |
| /replydraft <msg_id>\|<body> | Reply draft |
| /senddraft <draft_id> | Send draft |
| /drafts | List drafts |
| /inboxsummary | Inbox summary |
| /approvals | List pending approvals |
| /approve <id> | Approve an action |
| /reject <id> | Reject an action |
| /playbooks | List available workflows |
| /runworkflow <name> [\| params] | Run a workflow |
| /routineon <type> | Enable routine (morning/evening/reminders) |
| /routineoff <type> | Disable routine |
| /routinestatus | Routine status |
| /quieton / /quietoff / /quietstatus | Quiet hours control |
| /voiceon / /voiceoff / /voicestatus | Voice response control |
| /browserstart \<url\> | Start browser session at URL |
| /browserstatus | Status of current active session |
| /browsersessions | List all recent browser sessions |
| /browserclose [session_id] | Close a browser session |
| /browserresume \<session_id\> | Resume after manual login |
| /browserartifacts \<session_id\> | List screenshots/downloads for a session |
| /webresearch \<url\> | Research a website (website_research playbook) |
| /portcheck \<url\> | Check a portal for updates (portal_check playbook) |
| /formsession \<url\> [\| field=value ...] | Automated form session (form_prep playbook) |

### Key env vars (Python)

- `JARVIS_DATABASE_URL` — defaults to `sqlite:///./jarvis.db`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_ALLOWED_USER_ID` (string)
- `OPENAI_API_KEY`, `OPENAI_MODEL` (default: `gpt-5-mini`)
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
- `GOOGLE_OAUTH_SCOPES`, `GOOGLE_GMAIL_ENABLED`, `GOOGLE_GMAIL_SCOPES`
- `GMAIL_INBOX_QUERY_DEFAULT`, `GMAIL_MAX_LIST_RESULTS`
- `OPENAI_TRANSCRIBE_MODEL`, `OPENAI_TTS_MODEL`
- `VOICE_RESPONSES_ENABLED`, `VOICE_RESPONSE_VOICE`, `MAX_AUDIO_FILE_MB`
- `PROACTIVE_FEATURES_ENABLED` — enable proactive features (default: true)
- `MORNING_BRIEFING_ENABLED`, `MORNING_BRIEFING_TIME` — morning briefing (default: true, 07:30)
- `EVENING_REVIEW_ENABLED`, `EVENING_REVIEW_TIME` — evening review (default: true, 18:00)
- `QUIET_HOURS_ENABLED`, `QUIET_HOURS_START`, `QUIET_HOURS_END` — quiet hours (default: true, 22:00–07:00)
- `PROACTIVE_MIN_INTERVAL_MINUTES` — cooldown between proactive messages (default: 30)
- `MAX_PENDING_APPROVALS` — max pending approvals per user (default: 20)
- `REMINDER_CHECK_INTERVAL_MINUTES` — scheduler check interval (default: 10)
- `APP_ENV`, `TIMEZONE`, `APP_BASE_URL`
- `BROWSER_AUTOMATION_ENABLED` — master switch (default: false)
- `BROWSER_ALLOWED_DOMAINS` — comma-separated allowlist (e.g. `example.com,docs.python.org`); **empty = all navigation blocked**
- `BROWSER_HEADLESS` — run Chromium headless (default: true)
- `BROWSER_DEFAULT_TIMEOUT_MS` — default Playwright timeout (default: 10000)
- `BROWSER_NAVIGATION_TIMEOUT_MS` — page.goto timeout (default: 30000)
- `BROWSER_SESSION_TTL_MINUTES` — auto-expire idle sessions (default: 60)
- `BROWSER_SCREENSHOT_DIR` — where screenshots are stored (default: `/tmp/jarvis_screenshots`)
- `BROWSER_DOWNLOAD_DIR` — where downloads are saved (default: `/tmp/jarvis_downloads`)
- `BROWSER_ALLOW_FILE_DOWNLOADS` — allow page.expect_download (default: true)
- `BROWSER_REQUIRE_APPROVAL_FOR_SUBMIT` — route form submits through approval center (default: true)

### Key design decisions

- **user_id as String** everywhere (models, config, comparisons)
- **Single httpx.AsyncClient** in TelegramService (started in lifespan, stopped on shutdown)
- **Tool call round limit** (default 3) to prevent infinite loops in OpenAI function calling
- **Context limits**: configurable max messages (20) and max memories (10) per LLM call
- **All bot responses in pt-BR**
- **Webhook security order**: secret header → allowed user_id → idempotency → dispatch
- **Google OAuth**: access_type=offline, prompt=consent, state validation (CSRF protection)
- **Google fallback**: When not connected, /myday and /me/day return mock data
- **Phase 6 architecture**: suggestion_created → approval_created → approval_approved → approval_executed (each logged in ActionLog)
- **PendingApproval**: has `expires_at`, `idempotency_key` (unique constraint), `executed_at` for idempotency
- **Workflow params**: `/runworkflow lead_followup | Empresa X | email@x.com | contexto` — split by `|`
- **RoutineExecutionLog**: unique on (routine_type, run_key) for dedup — run_key = e.g. `briefing_2026-03-15`
- **Scheduler**: asyncio task started in lifespan, checks routines every `reminder_check_interval_minutes`
- **Quiet hours**: global setting + per-user MemoryItem(category="preference", content="quiet_hours_disabled")
- **Cooldown**: checked via ActionLog("proactive_message_sent") recency
- **Browser architecture**: single shared `_browser` + `_playwright` globals per process; `start_browser()`/`stop_browser()` in lifespan; `_live_contexts` maps session_id → (context, page) in memory
- **Browser domain enforcement**: `is_domain_allowed(url)` blocks every navigation — empty `BROWSER_ALLOWED_DOMAINS` = all blocked; subdomain matching supported
- **Browser one-session-per-user**: attempting a second session while one is active returns an error
- **Login detection**: URL/title patterns (login, signin, sign-in, auth, password, 2fa, verify) OR password input → session pauses to `paused_for_login`; use /browserresume to continue
- **Sensitive action routing**: `is_sensitive_action()` checks action type + selector text + URL pattern; sensitive actions create a PendingApproval and return `pending_approval` status; approval dispatch calls `approve_and_execute_browser_action`
- **Downloads**: `page.expect_download()` async context manager + `download.save_as(path)`; saved to `BROWSER_DOWNLOAD_DIR`, recorded in BrowserArtifact
- **Browser cleanup**: scheduler runs `expire_old_sessions` + `clean_old_browser_artifacts` hourly via `browser_cleanup` run_key
- **12 browser OpenAI tools**: browser_start_session, browser_open_url, browser_click, browser_fill, browser_select_option, browser_press_key, browser_wait_for_selector, browser_capture_screenshot, browser_extract_visible_text, browser_download_file, browser_close_session, browser_list_sessions
- **4 browser playbooks**: website_research, form_prep, portal_check, file_collect

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
