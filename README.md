# 📡 SiteWatcher

> Website uptime monitoring with real-time Telegram and email alerts.

**Live demo (frontend):** https://sitewatcher-six.vercel.app
**Live API (backend):** https://sitewatch-1k5k.onrender.com

---

## Features

- **Uptime monitoring** — checks your sites every 1–60 minutes
- **Telegram alerts** — instant notifications when a site goes down or recovers
- **Email alerts** — optional additional notifications via Resend
- **Email confirmation** — new accounts must confirm their address before signing in
- **Response time tracking** — detects slow responses before users notice
- **Content change detection** — alerts when page content changes (Pro)
- **Check history** — full log with response times and status codes
- **Freemium model** — free tier for 1 site, Pro for up to 50

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, APScheduler |
| Database | PostgreSQL + SQLAlchemy 2.0 (async) |
| Auth | JWT (python-jose) + bcrypt |
| HTTP checks | httpx (async) |
| Content diff | BeautifulSoup4 + MD5 hash |
| Notifications | Telegram Bot API + Resend |
| Payments | Telegram Stars |
| Frontend | React 18, Vite, Tailwind CSS |
| Deploy | Docker, Render.com |

---

## Project Structure

```
sitewatcher/
├── backend/
│   └── app/
│       ├── api/          # FastAPI routers: auth, sites, billing, telegram
│       ├── models/       # SQLAlchemy models: User, Site, CheckLog
│       ├── services/     # checker, scheduler, auth, telegram
│       └── core/         # config, settings
├── frontend/
│   └── src/
│       ├── pages/        # Dashboard, Auth, Settings, Upgrade
│       └── components/   # SiteCard, AddSiteModal, Logs, Chart
├── docker-compose.yml
└── setup_webhook.py      # Register Telegram webhook
```

---

## Running Locally

### Prerequisites
- Docker + Docker Compose
- Telegram Bot token (from [@BotFather](https://t.me/BotFather))

### 1. Clone and configure

```bash
git clone https://github.com/epetrovich0/sitewatcher.git
cd sitewatcher
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```env
DATABASE_URL=postgresql+asyncpg://user:password@db:5432/sitewatcher
SECRET_KEY=your-secret-key-here
TELEGRAM_BOT_TOKEN=your-bot-token
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxx
RESEND_FROM_EMAIL=no-reply@example.com
RESEND_FROM_NAME=SiteWatcher
FRONTEND_URL=http://localhost:5173
ADMIN_SECRET=your-admin-secret
ENV=development
```

### 2. Start

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

### 3. Register Telegram webhook (for alerts)

```bash
export TELEGRAM_BOT_TOKEN=your-token
python3 setup_webhook.py http://your-public-url.com
```

> For local development use [ngrok](https://ngrok.com) to expose localhost.

---

## API Overview

```
POST /api/auth/register     Register new user
GET  /api/auth/verify-email Confirm email via link
POST /api/auth/login        Login, returns JWT
GET  /api/auth/me           Current user info
PATCH /api/auth/me/notifications  Configure email alerts

GET  /api/sites/            List monitored sites
POST /api/sites/            Add site (free: 1, pro: 50)
DELETE /api/sites/{id}      Remove site
POST /api/sites/{id}/check-now   Trigger immediate check
GET  /api/sites/{id}/logs   Check history

POST /api/billing/send-invoice       Pay with Telegram Stars
POST /api/billing/stripe-checkout     Pay with Stripe Checkout
POST /api/billing/admin/activate/{email}?secret=  Manual Pro activation
```

---

## Monitoring Logic

```
Every minute → scheduler wakes up
    → finds sites where next_check_at <= now
    → async HTTP GET with 15s timeout
    → saves CheckLog (status, response_time, content_hash)
    → compares with previous status
    → if site went DOWN → send Telegram alert
    → if site RECOVERED → send Telegram alert
    → if response_time > threshold → send slow alert (Pro)
    → if content changed → send change alert (Pro)
    → updates next_check_at = now + check_interval
```

---

## Deployment

Both services are deployed on [Render.com](https://render.com) free tier:

- **Backend** — Docker web service
- **Frontend** — Static site (Vite build)
- **Database** — Render PostgreSQL

Required environment variables on Render:

```env
DATABASE_URL         # Render PostgreSQL internal URL (postgresql+asyncpg://...)
SECRET_KEY           # Random string for JWT signing
TELEGRAM_BOT_TOKEN   # From @BotFather
FRONTEND_URL         # https://sitewatcher-six.vercel.app
ADMIN_SECRET         # Secret for manual Pro activation
STRIPE_SECRET_KEY    # Stripe secret key
STRIPE_WEBHOOK_SECRET # Stripe webhook signing secret
STRIPE_SUCCESS_URL   # Stripe success redirect URL
STRIPE_CANCEL_URL    # Stripe cancel redirect URL
RESEND_API_KEY       # Resend API key (resend.com)
RESEND_FROM_EMAIL    # Verified sender email
RESEND_FROM_NAME     # Optional sender display name
ENV                  # production (hides /docs)
```

---

## Free vs Pro

| Feature | Free | Pro |
|---|---|---|
| Monitored sites | 1 | 50 |
| Check interval | 60 min | 1 min |
| Uptime monitoring | ✅ | ✅ |
| Response time alerts | ✅ | ✅ |
| Content change detection | ❌ | ✅ |
| Telegram alerts | ✅ | ✅ |

**Payment options:**
- Telegram Stars (instant, built-in)
- Stripe Checkout (card payment)

---

## License

MIT
