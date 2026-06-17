# 📡 SiteWatcher

> Telegram-native website uptime monitoring with AI hints and email alerts.

**Live demo (frontend):** https://sitewatcher-six.vercel.app
**Live API (backend):** https://sitewatch-1k5k.onrender.com
**Repository:** https://github.com/sinitski/sitewatcher

---

## Features

- **Uptime monitoring** — checks your sites every 1–60 minutes
- **Telegram alerts** — instant notifications when a site goes down or recovers
- **Email alerts** — optional additional notifications via Gmail API
- **Email confirmation** — new accounts must confirm their address before signing in
- **Response time tracking** — detects slow responses before users notice
- **Content change detection** — alerts when page content changes (Pro)
- **Check history** — full log with response times and status codes
- **Freemium model** — free tier for 1 site, Pro for up to 50
- **Enterprise foundations** — org RBAC, audit logs, webhook/Slack channels, SLO exports, SCIM users API

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, APScheduler |
| Database | PostgreSQL + SQLAlchemy 2.0 (async) |
| Auth | JWT (python-jose) + bcrypt |
| HTTP checks | httpx (async) |
| Content diff | BeautifulSoup4 + MD5 hash |
| Notifications | Telegram Bot API + Gmail API |
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
git clone https://github.com/sinitski/sitewatcher.git
cd sitewatcher
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```env
DATABASE_URL=postgresql+asyncpg://user:password@db:5432/sitewatcher
SECRET_KEY=your-secret-key-here
TELEGRAM_BOT_TOKEN=your-bot-token
GMAIL_CLIENT_ID=xxxxxxxxxxxxxxxx.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=xxxxxxxxxxxxxxxx
GMAIL_REFRESH_TOKEN=xxxxxxxxxxxxxxxx
GMAIL_SENDER_EMAIL=your@gmail.com
FRONTEND_URL=http://localhost:5173
ADMIN_SECRET=your-admin-secret
ENV=development

# Optional hardening/reliability settings
CORS_ALLOW_ORIGINS=http://localhost:5173,http://localhost:3000
RATE_LIMIT_LOGIN_PER_MINUTE=30
RATE_LIMIT_REGISTER_PER_MINUTE=10
RATE_LIMIT_VERIFICATION_PER_MINUTE=10
SCHEDULER_MAX_CONCURRENT_CHECKS=20
CHECK_RETRY_COUNT=1
CHECK_RETRY_BACKOFF_SECONDS=2
NEXT_CHECK_JITTER_SECONDS=20
CONTENT_CHANGE_ALERT_COOLDOWN_MINUTES=30
CHECK_LOCATIONS=edge-a,edge-b

# Enterprise (optional)
OIDC_AUTH_URL=
OIDC_CLIENT_ID=
OIDC_REDIRECT_URI=
SCIM_BEARER_TOKEN=
LOG_RETENTION_DAYS=90
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
| Health Live | http://localhost:8000/health/live |
| Health Ready | http://localhost:8000/health/ready |

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
POST /api/billing/paypal-checkout     Pay with PayPal Checkout
POST /api/billing/paypal-capture      Capture PayPal order after return
POST /api/billing/admin/activate/{email}?secret=  Manual Pro activation

GET  /api/status/{slug}       Public status page data
GET  /api/status/me/summary   Authenticated status summary and growth metrics

POST /api/enterprise/orgs                      Create organization
GET  /api/enterprise/orgs                      List organizations for current user
POST /api/enterprise/orgs/{id}/members         Add/update org member
GET  /api/enterprise/orgs/{id}/audit           Immutable audit logs
POST /api/enterprise/orgs/{id}/channels        Add Slack/webhook channel
POST /api/enterprise/orgs/{id}/maintenance     Add maintenance window
GET  /api/enterprise/orgs/{id}/slo-summary     SLO summary
GET  /api/enterprise/orgs/{id}/slo-export.csv  SLA/SLO CSV export
GET  /api/enterprise/scim/v2/Users             SCIM Users (read-only)
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
PAYPAL_CLIENT_ID     # PayPal REST client id
PAYPAL_CLIENT_SECRET # PayPal REST client secret
PAYPAL_MODE          # sandbox or live
PAYPAL_SUCCESS_URL   # PayPal success redirect URL
PAYPAL_CANCEL_URL    # PayPal cancel redirect URL
GMAIL_CLIENT_ID      # Google OAuth client id
GMAIL_CLIENT_SECRET  # Google OAuth client secret
GMAIL_REFRESH_TOKEN  # Google OAuth refresh token with gmail.send scope
GMAIL_SENDER_EMAIL   # Sender email in Gmail account
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
| Email alerts | 1/day | Unlimited |

**Payment options:**
- Telegram Stars (instant, built-in)
- PayPal Checkout (international card payment)

---

## License

MIT
