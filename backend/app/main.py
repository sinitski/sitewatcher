import logging
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import traceback
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.db.database import init_db
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.notification_queue import start_notification_workers, stop_notification_workers
from app.api import auth, sites, telegram, billing, status, enterprise
from app.core.config import settings
import os

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up SiteWatcher...")
    await init_db()
    start_notification_workers()
    start_scheduler()
    yield
    logger.info("Shutting down...")
    stop_scheduler()
    await stop_notification_workers()


IS_PRODUCTION = os.getenv("ENV") == "production"

app = FastAPI(
    title="SiteWatcher API",
    version="1.0.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ALLOW_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(sites.router, prefix="/api")
app.include_router(telegram.router, prefix="/api")
app.include_router(billing.router, prefix="/api")
app.include_router(status.router, prefix="/api")
app.include_router(enterprise.router, prefix="/api")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: https:; connect-src 'self' https:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
        return response


app.add_middleware(SecurityHeadersMiddleware)

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow()}


@app.get("/health/live")
async def health_live():
    return {"status": "alive", "time": datetime.utcnow()}


@app.api_route("/health/ready", methods=["GET", "HEAD"])
async def health_ready():
    from sqlalchemy import text
    from app.db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ready", "time": datetime.utcnow()}

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": traceback.format_exc()}
    )