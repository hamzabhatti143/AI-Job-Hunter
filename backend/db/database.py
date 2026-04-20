import os
import ssl
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Engine is created lazily — no connection attempt at import time
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,      # recycle connections every 5 min — prevents Neon cold starts
    pool_timeout=30,
    connect_args={
        **({"ssl": ssl_context} if DATABASE_URL else {}),
        "statement_cache_size": 0,        # required for Neon pgBouncer — avoids prepared-statement errors/retries
        "prepared_statement_cache_size": 0,
        "server_settings": {"application_name": "applyai"},
    },
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def verify_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable not set")
    from sqlalchemy import text
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
