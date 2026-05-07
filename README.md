# Job Alert Bot

Telegram bot that scrapes multiple job portals and pushes filtered alerts
to users. Monetised via Rs. 99/month premium tier.

> **Status:** All phases complete and ready for deployment.

---

## Stack

Python 3.12 · FastAPI · python-telegram-bot v20 · PostgreSQL 15 · Redis 7
APScheduler · httpx · BeautifulSoup4 · Razorpay · Docker

---

## Quick start (local dev)

```powershell
# 1. Copy env and fill in TELEGRAM_BOT_TOKEN (minimum required)
copy .env.example .env

# 2. Create virtualenv and install deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. Start Postgres + Redis
docker compose up -d

# 4. Run migrations
python -m app.db.migrate

# 5. Start the API (bot runs in polling mode when WEBHOOK_URL is empty)
uvicorn app.main:app --reload --port 8000
```

---

## Deployment (Docker)

```bash
docker build -t jobalertbot .
docker run -p 8000:8000 --env-file .env jobalertbot
```

Set `WEBHOOK_URL` to your public URL so Telegram sends updates via webhook
instead of polling.

---

## Project layout

```
jobsearcher/
├── app/
│   ├── main.py                          # FastAPI app + lifespan
│   ├── config.py                        # pydantic-settings
│   ├── api/routes/
│   │   ├── webhook.py                   # POST /webhook/telegram
│   │   └── payments.py                  # POST /webhook/razorpay
│   ├── bot/
│   │   ├── application.py               # PTB Application builder + singleton
│   │   └── handlers/
│   │       ├── commands.py              # /start  /help
│   │       ├── onboarding.py            # /setskills /setcity /setexperience /pause /resume /profile
│   │       └── subscribe.py             # /subscribe
│   ├── matching/
│   │   └── engine.py                    # SQL matcher + alert formatter
│   ├── scraper/
│   │   ├── base.py                      # JobData + BaseJobScraper
│   │   ├── scheduler.py                 # APScheduler jobs
│   │   └── sources/
│   │       ├── naukri.py                # Naukri internal JSON API
│   │       └── remoteok.py              # RemoteOK public API
│   └── db/
│       ├── connection.py                # asyncpg pool
│       ├── redis.py                     # Redis client
│       ├── migrate.py                   # SQL migration runner
│       ├── users.py                     # users table queries
│       ├── jobs.py                      # jobs table bulk upsert
│       ├── alerts.py                    # alerts_sent table
│       ├── payments.py                  # payments + subscriptions
│       └── migrations/0001_init.sql
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Bot commands

| Command | Description |
|---|---|
| /start | Register + welcome message |
| /setskills python,django | Set skill preferences |
| /setcity bangalore,remote | Set city + remote flag |
| /setexperience 2_5 | Set experience band (fresher / 0_2 / 2_5 / 5_10 / 10_plus) |
| /pause | Stop receiving alerts |
| /resume | Resume alerts |
| /profile | View current settings |
| /subscribe | Upgrade to Premium (Rs. 99/mo) |
| /help | Show command list |

---

## Adding a new scraper source

1. Create `app/scraper/sources/<name>.py` — subclass `BaseJobScraper`, set `source = "<name>"`, implement `scrape()`.
2. Add a `_run_<name>` coroutine in `app/scraper/scheduler.py`.
3. Register it with `_scheduler.add_job(...)` inside `get_scheduler()`.

That's it — DB upsert, dedup, and matching are source-agnostic.

---

## Stopping

```powershell
# Stop API: Ctrl+C
docker compose down          # keeps data
docker compose down -v       # wipes Postgres + Redis
```
