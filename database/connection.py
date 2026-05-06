from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from database.models import Base

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
_engine_kwargs = {"echo": False}
if not _is_sqlite:
    _engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if _is_sqlite:
        await _sqlite_migrations()


async def _sqlite_migrations() -> None:
    """Add columns introduced after initial schema creation."""
    migrations = [
        # Existing
        ("users", "referral_link_id", "INTEGER REFERENCES referral_links(id)"),
        # Reputation & stats
        ("users", "level",                   "TEXT NOT NULL DEFAULT 'newbie'"),
        ("users", "completed_orders",        "INTEGER NOT NULL DEFAULT 0"),
        ("users", "total_earned",            "REAL NOT NULL DEFAULT 0.0"),
        ("users", "total_spent",             "REAL NOT NULL DEFAULT 0.0"),
        ("users", "notifications_enabled",   "INTEGER NOT NULL DEFAULT 1"),
        # Deal auto-release
        ("deals", "submission_time",  "DATETIME"),
        ("deals", "auto_release_at",  "DATETIME"),
        ("deals", "auto_released",    "INTEGER NOT NULL DEFAULT 0"),
        # Job promotion
        ("jobs", "is_boosted",      "INTEGER NOT NULL DEFAULT 0"),
        ("jobs", "is_vip",          "INTEGER NOT NULL DEFAULT 0"),
        ("jobs", "promoted_until",  "DATETIME"),
        # Message file sharing
        ("messages", "message_type", "TEXT NOT NULL DEFAULT 'text'"),
        ("messages", "file_id",      "TEXT"),
        ("messages", "filename",     "TEXT"),
        # Message text nullable (was NOT NULL)
        # Note: SQLite can't ALTER COLUMN, existing rows will have text value
        # Service promotion
        ("services", "is_promoted",    "INTEGER NOT NULL DEFAULT 0"),
        ("services", "promoted_until", "DATETIME"),
        # Dual balance + verified
        ("users", "balance_ton", "REAL NOT NULL DEFAULT 0.0"),
        ("users", "is_verified", "INTEGER NOT NULL DEFAULT 0"),
        # Deal escrow currency + dispute tracking
        ("deals", "escrow_currency",   "TEXT NOT NULL DEFAULT 'usd'"),
        ("deals", "escrow_ton_amount", "REAL"),
        ("deals", "dispute_opened_at", "DATETIME"),
    ]
    async with engine.begin() as conn:
        for table, col, col_def in migrations:
            result = await conn.execute(text(f"PRAGMA table_info({table})"))
            existing = {row[1] for row in result.fetchall()}
            if col not in existing:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))


async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session
