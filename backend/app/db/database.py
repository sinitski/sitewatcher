from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import inspect, text
from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        from app.models import user, site, check, payment, incident, product_event, organization, organization_member, audit_log, notification_channel, maintenance_window  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

        def ensure_user_referral_columns(sync_conn):
            inspector = inspect(sync_conn)
            columns = {col["name"] for col in inspector.get_columns("users")}

            if "email_verified" not in columns:
                sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE")
            if "email_verification_token" not in columns:
                sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN email_verification_token VARCHAR")
            if "email_verification_expires_at" not in columns:
                sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN email_verification_expires_at TIMESTAMP")
            if "email_alerts_enabled" not in columns:
                sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN email_alerts_enabled BOOLEAN NOT NULL DEFAULT FALSE")
            if "alert_emails" not in columns:
                sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN alert_emails VARCHAR")
            if "status_slug" not in columns:
                sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN status_slug VARCHAR")

            if "referral_code" not in columns:
                sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN referral_code VARCHAR")
            if "referred_by_user_id" not in columns:
                sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN referred_by_user_id INTEGER")
            if "referral_bonus_sites" not in columns:
                sync_conn.exec_driver_sql("ALTER TABLE users ADD COLUMN referral_bonus_sites INTEGER NOT NULL DEFAULT 0")

            sync_conn.exec_driver_sql("UPDATE users SET email_verified = TRUE WHERE email_verified IS NULL OR email_verified = FALSE")

            users_without_code = sync_conn.exec_driver_sql(
                "SELECT id FROM users WHERE referral_code IS NULL OR referral_code = ''"
            ).fetchall()
            for row in users_without_code:
                user_id = row[0]
                # Keep generation simple and deterministic enough for migrations.
                new_code = f"U{user_id:07d}"
                sync_conn.execute(
                    text("UPDATE users SET referral_code = :code WHERE id = :id"),
                    {"code": new_code, "id": user_id},
                )

            dialect = sync_conn.dialect.name
            if dialect == "postgresql":
                sync_conn.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_referral_code ON users (referral_code)"
                )
                sync_conn.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_verification_token ON users (email_verification_token)"
                )
                sync_conn.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_status_slug ON users (status_slug)"
                )
            elif dialect == "sqlite":
                index_rows = sync_conn.exec_driver_sql("PRAGMA index_list('users')").fetchall()
                index_names = {row[1] for row in index_rows}
                if "ix_users_referral_code" not in index_names:
                    sync_conn.exec_driver_sql(
                        "CREATE UNIQUE INDEX ix_users_referral_code ON users (referral_code)"
                    )
                if "ix_users_email_verification_token" not in index_names:
                    sync_conn.exec_driver_sql(
                        "CREATE UNIQUE INDEX ix_users_email_verification_token ON users (email_verification_token)"
                    )
                if "ix_users_status_slug" not in index_names:
                    sync_conn.exec_driver_sql(
                        "CREATE UNIQUE INDEX ix_users_status_slug ON users (status_slug)"
                    )

            users_without_slug = sync_conn.exec_driver_sql(
                "SELECT id, email FROM users WHERE status_slug IS NULL OR status_slug = ''"
            ).fetchall()
            for row in users_without_slug:
                user_id = row[0]
                email = row[1] or ""
                slug = email.split("@")[0].lower().replace(" ", "-") if "@" in email else f"u{user_id}"
                slug = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in slug).strip("-")
                if not slug:
                    slug = f"u{user_id}"
                suffix = 1
                candidate = slug
                while True:
                    exists = sync_conn.execute(
                        text("SELECT 1 FROM users WHERE status_slug = :slug AND id != :id"),
                        {"slug": candidate, "id": user_id},
                    ).fetchone()
                    if not exists:
                        break
                    suffix += 1
                    candidate = f"{slug}-{suffix}"
                sync_conn.execute(
                    text("UPDATE users SET status_slug = :slug WHERE id = :id"),
                    {"slug": candidate, "id": user_id},
                )

        await conn.run_sync(ensure_user_referral_columns)

        def ensure_check_columns(sync_conn):
            inspector = inspect(sync_conn)
            columns = {col["name"] for col in inspector.get_columns("check_logs")}

            if "email_sent" not in columns:
                sync_conn.exec_driver_sql("ALTER TABLE check_logs ADD COLUMN email_sent BOOLEAN NOT NULL DEFAULT FALSE")

        await conn.run_sync(ensure_check_columns)
