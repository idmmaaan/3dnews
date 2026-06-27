# 📰 News-3Twit — Automated News Curation Pipeline

> **Twitter → LLM → Telegram** — Fetch tweets from mainstream media accounts, summarise in English via Gemini, and publish to a Telegram channel. Fully automated, running every 15 minutes.

---

## Architecture

```
┌──────────────┐   fetch    ┌──────────────┐  summarise   ┌──────────┐
│  Twitter /X  │ ────────►  │   FastAPI +   │ ──────────►  │  OpenAI  │
│   API v2     │            │  APScheduler  │              │  GPT-4o  │
└──────────────┘            │               │              └──────────┘
                            │  PostgreSQL   │                   │
                            │  (dedup DB)   │  ◄────────────────┘
                            └───────┬───────┘   English summary
                                    │
                                    │ post
                                    ▼
                            ┌──────────────┐
                            │   Telegram    │
                            │   Channel    │
                            └──────────────┘
```

## Tech Stack

| Layer         | Technology                          |
|---------------|-------------------------------------|
| Runtime       | Python 3.11+                        |
| Framework     | FastAPI + APScheduler               |
| Database      | PostgreSQL 16 + SQLAlchemy 2.0      |
| Migrations    | Alembic (async)                     |
| Twitter       | httpx (Twitter API v2)              |
| LLM           | Google Gemini (`gemini-2.5-flash`)  |
| Telegram      | aiogram v3                          |
| Config        | pydantic-settings                   |
| Deployment    | Docker & Docker Compose             |

## Quick Start

### 1. Clone & configure

```bash
cp .env.example .env
# Fill in your real API keys in .env
```

### 2. Start with Docker Compose

```bash
docker compose up --build -d
```

This will:
- Start PostgreSQL 16
- Run Alembic migrations automatically
- Launch the FastAPI server on port `8000`
- Begin polling Twitter every 15 minutes

### 3. Verify

```bash
# Health check
curl http://localhost:8000/health

# Manual pipeline trigger
curl -X POST http://localhost:8000/trigger
```

## Project Structure

```
news-3twit/
├── app/
│   ├── main.py              # FastAPI app + scheduler
│   ├── core/
│   │   ├── config.py         # pydantic-settings
│   │   └── database.py       # async SQLAlchemy engine
│   ├── models/
│   │   └── tweet.py          # ProcessedTweet ORM model
│   ├── services/
│   │   ├── twitter.py        # Twitter API v2 fetcher
│   │   ├── llm.py            # Gemini English summarization
│   │   ├── telegram.py       # aiogram v3 posting
│   │   └── pipeline.py       # Orchestrator
│   └── api/
│       └── routes.py         # /health, /trigger
├── alembic/                  # Database migrations
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

## Database Migrations

```bash
# Generate a new migration after changing models
alembic revision --autogenerate -m "describe your change"

# Apply migrations
alembic upgrade head
```

## Environment Variables

| Variable               | Description                                      | Default              |
|------------------------|--------------------------------------------------|----------------------|
| `DATABASE_URL`         | PostgreSQL connection string (asyncpg)           | see `.env.example`   |
| `TWITTER_BEARER_TOKEN` | Twitter API v2 Bearer token                      | —                    |
| `TWITTER_USERNAMES`    | Comma-separated Twitter handles to monitor       | `CNN,BBCWorld,Reuters` |
| `OPENAI_API_KEY`       | OpenAI API key                                   | —                    |
| `OPENAI_MODEL`         | OpenAI model to use                              | `gpt-4o-mini`        |
| `TELEGRAM_BOT_TOKEN`   | Telegram Bot API token                           | —                    |
| `TELEGRAM_CHANNEL_ID`  | Telegram channel (e.g. `@my_channel`)            | —                    |
| `POLL_INTERVAL_MINUTES`| How often to poll Twitter (minutes)              | `15`                 |

## License

MIT
# 3dnews
