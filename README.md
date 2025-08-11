# Distill — Telegram Summarizer Bot

Turn noisy Telegram feeds into a clean, personalized daily brief. Distill collects posts from public channels you choose, semantically filters them against your topics, summarizes what matters, and delivers it to you in Telegram.

## Features

- Personalized topic tracking: add/remove topics you care about
- Source curation: follow specific public channels (e.g., @channelname or t.me links)
- Daily summaries at a fixed time (Europe/Kyiv) with engaging, concise formatting
- Multilingual UX (English, Ukrainian) with per-user language setting
- Vector search filtering via Qdrant for semantic relevance
- Embeddings: OpenAI
- Admin monitoring via Telegram notifications and structured JSON logs

## Architecture at a glance

1) Collect: fetch recent messages from users’ followed sources using Telethon
2) Embed: generate vector embeddings for messages and upsert to Qdrant
3) Filter: for each user, vector-search per topic against their followed sources
4) Summarize: generate a digest with Gemini (Google Generative AI)
5) Deliver: send summary to each user via Telegram bot

Key modules (under `src/`):

- `bot/` — Telegram bot, conversation flow, menus, scheduling
- `pipeline/collector.py` — Telegram collection, embeddings, Qdrant upsert
- `pipeline/filter.py` — Qdrant vector search per user & topic
- `pipeline/summarizer.py` — Gemini-based summary generation and formatting
- `db/` — SQLAlchemy models and session management
- `utils/` — i18n, logging, monitoring, embedding providers, validation, stats

Data model highlights (`src/db/models.py`):

- `User`, `Source`, `Message`, `UserTopic`, `FilteredMessage`, `Summary`, `ProcessingStats`

## Tech stack

- Python 3.11+
- Telegram: `python-telegram-bot` (bot), `telethon` (collection)
- Vector DB: Qdrant
- LLM: Google Gemini (`google-genai`)
- Embeddings: OpenAI
- ORM: SQLAlchemy

## Prerequisites

- Python 3.11+
- Qdrant instance (Cloud or self-hosted), reachable via `QDRANT_URL`
- Telegram credentials (API ID, API Hash, phone) and a bot token
- Gemini API key for summaries
- OpenAI API key if using OpenAI embeddings

## Quickstart

1) Clone and enter the project

```powershell
git clone https://github.com/Vladoverx/tg-summarizer.git
Set-Location tg-summarizer
```

```bash
# Linux/macOS
git clone https://github.com/Vladoverx/tg-summarizer.git
cd tg-summarizer
```

2) Create your environment file

```powershell
Copy-Item env.example .env
# Open .env and fill in values (see table below)
```

```bash
# Linux/macOS
cp env.example .env
# Open .env and fill in values (see table below)
```

3) Run with Docker Compose (recommended)


```bash
# Linux/macOS
docker compose up -d --build
```

4) One-time Telethon login (required)

Telethon needs a one-time, interactive login to create a session file. Do this once after starting the container; the session will be persisted under `./data`.

- Open a shell in the running container:

```powershell
docker compose exec app sh
```

- Run the login helper (follow prompts for the code and 2FA password if enabled):
  Preferred (uses project deps):

```sh
uv run tg-login
```

  If `uv` is not available in the container for any reason, you can still run the module directly:

```sh
python -m utils.telethon_login
```

Expected:

- You see `Authorized: True`.
- A session file appears on the host at `./data/collector_session.session` (or matching `TELEGRAM_SESSION_NAME`).

- Exit the container shell:

```sh
exit
```

Optional: restart the app service to ensure a clean state

```powershell
docker compose restart app
```

Alternative: run locally

- Using uv:

```bash
# Linux/macOS
uv sync
uv run tg-bot
```

- Using pip:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
tg-bot
# or: python -m bot.main
```

```bash
# Linux/macOS
python -m venv .venv
source .venv/bin/activate
pip install -e .
tg-bot
# or: python -m bot.main
```


## Configuration (.env)

Database

- `DATABASE_URL` — SQLAlchemy URL (e.g., `sqlite:///./tg_summarizer.db`)
- `SQL_ECHO` — `true`/`false` to echo SQL

Telegram

- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE` — account used by the collector (required)
- `BOT_TOKEN` — Telegram bot token
- `ADMIN_CHAT_ID` — chat ID for admin notifications (optional but recommended)

Qdrant

- `QDRANT_URL` — endpoint (e.g., `https://xxxxxxxx.qdrant.cloud`)
- `QDRANT_API_KEY` — API key if required by your instance

LLM and embeddings

- `GEMINI_API_KEY` — required for summaries
- `OPENAI_API_KEY` — required for embeddings

Notes

- OpenAI embeddings default model: `text-embedding-3-small` (1536-dim).
 - Telethon session file is stored under `./data` by default (`TELEGRAM_SESSION_NAME` defaults to `/data/collector_session` inside the container). Perform the one-time login as shown above.

## What happens at runtime

Scheduling (Kyiv timezone):

- 17:45 — collect and filter (`collector` → `filter`)
- 18:00 — generate and send daily summaries
- 19:00 — check inactive users (admin notification)

Bot UX:

- Manage topics and sources via menu buttons
- Change language (English/Українська)
- Admin-only testing menu to manually run collection or generate summaries

Logging and monitoring:

- Logs: JSON logs written to `logs/app.log` with daily rotation
- Admin notifications: operational events and errors sent to `ADMIN_CHAT_ID`

Vector search and filtering:

- Messages are embedded and stored in Qdrant collection `tg-summarizer`
- Per user/topic, the filter queries Qdrant with a score threshold and saves matches to `filtered_messages`

Summary generation:

- For users with topics: topic-based JSON schema → formatted HTML/Markdown
- Without topics: source-based deduplication summary

## Troubleshooting

- Missing Qdrant config: set `QDRANT_URL` (and `QDRANT_API_KEY` if needed)
- Missing Gemini key: set `GEMINI_API_KEY`
- OpenAI embeddings enabled but no key: set `OPENAI_API_KEY`
- Telegram 2FA: Telethon will require manual handling if 2FA is enabled on the collector account
- Rate limits: Telethon may raise `FloodWaitError`; the collector backs off automatically
- EOF / AuthKeyUnregistered errors when validating sources: perform the one-time Telethon login inside the container (see Quickstart step 4) so the session file is created and persisted.

## Deploy with Docker Compose

Prerequisites:

- Docker Desktop with Compose

Steps:

1) Create and fill your `.env`

```powershell
Copy-Item env.example .env
# Edit .env and set BOT_TOKEN, TELEGRAM_API_ID/HASH/PHONE, GEMINI_API_KEY, etc.
```

```bash
# Linux/macOS
cp env.example .env
# Edit .env and set BOT_TOKEN, TELEGRAM_API_ID/HASH/PHONE, GEMINI_API_KEY, etc.
```

2) Start the stack

```powershell
docker compose up -d --build
```

```bash
# Linux/macOS
docker compose up -d --build
```

This will start the bot container (`app`). Use your cloud Qdrant endpoint via `QDRANT_URL`.

Data and state:

- SQLite DB is persisted under `./data` (default `DATABASE_URL` resolves to `sqlite:////data/tg_summarizer.db` inside the container)
- Logs are written to `./logs`
- Telethon session is stored as `./data/collector_session.session` (configurable via `TELEGRAM_SESSION_NAME`)

Environment notes:

- Set `QDRANT_URL` to your cloud endpoint (e.g., `https://xxxxxxxx.qdrant.cloud`) and `QDRANT_API_KEY` if your instance requires it.

Common commands:

```powershell
docker compose logs -f app
docker compose restart app
docker compose down
```

```bash
# Linux/macOS
docker compose logs -f app
docker compose restart app
docker compose down
```

## Development notes

- Entry points (from `pyproject.toml`):
  - `tg-bot` → `bot.main:main`
- Code style: modern Python, explicit types, minimal comments, clear names

## License
 
Apache License 2.0. See `LICENSE` for full text.

