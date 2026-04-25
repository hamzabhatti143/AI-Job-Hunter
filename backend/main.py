import os
import sys
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# Force UTF-8 output on Windows so unicode chars don't crash startup
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from db.database import verify_db_connection, AsyncSessionLocal
        await verify_db_connection()
        print("[OK] Database connected")

        # Safe schema migrations — add new columns/tables without breaking existing data
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            migrations = [
                # New columns on job_matches
                "ALTER TABLE job_matches ADD COLUMN IF NOT EXISTS match_tier TEXT;",
                "ALTER TABLE job_matches ADD COLUMN IF NOT EXISTS source TEXT;",
                "ALTER TABLE job_matches ADD COLUMN IF NOT EXISTS portal_type TEXT;",
                "ALTER TABLE job_matches ADD COLUMN IF NOT EXISTS matched_skills JSONB;",
                "ALTER TABLE job_matches ADD COLUMN IF NOT EXISTS missing_skills JSONB;",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS resume_original_name TEXT;",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS gmail_access_token TEXT;",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS gmail_refresh_token TEXT;",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS gmail_token_expiry TIMESTAMPTZ;",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_client_id TEXT;",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_client_secret TEXT;",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_redirect_uri TEXT;",
                "ALTER TABLE sent_emails ADD COLUMN IF NOT EXISTS gmail_thread_id TEXT;",
                "ALTER TABLE sent_emails ADD COLUMN IF NOT EXISTS replied_at TIMESTAMPTZ;",
                "ALTER TABLE sent_emails ADD COLUMN IF NOT EXISTS reply_content TEXT;",
                # Portal accounts table
                """
                CREATE TABLE IF NOT EXISTS portal_accounts (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    portal_name TEXT NOT NULL,
                    portal_url TEXT NOT NULL,
                    username TEXT NOT NULL,
                    encrypted_password TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    last_used_at TIMESTAMPTZ
                );
                """,
                # Applications table
                """
                CREATE TABLE IF NOT EXISTS applications (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    job_id UUID REFERENCES job_matches(id) ON DELETE CASCADE,
                    method TEXT NOT NULL,
                    portal_name TEXT,
                    confirmation_id TEXT,
                    status TEXT DEFAULT 'submitted',
                    applied_at TIMESTAMPTZ DEFAULT now(),
                    notes JSONB
                );
                """,
                # Notifications table
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    is_read BOOLEAN DEFAULT false,
                    created_at TIMESTAMPTZ DEFAULT now()
                );
                """,
                # Portal blacklist table
                """
                CREATE TABLE IF NOT EXISTS portal_blacklist (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    portal_name TEXT NOT NULL,
                    portal_url TEXT,
                    reason TEXT,
                    failure_count INTEGER DEFAULT 1,
                    last_failed_at TIMESTAMPTZ DEFAULT now()
                );
                """,
                # Resume versions table
                """
                CREATE TABLE IF NOT EXISTS resume_versions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    version_number INTEGER NOT NULL DEFAULT 1,
                    label TEXT,
                    file_path TEXT NOT NULL,
                    notes TEXT,
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMPTZ DEFAULT now()
                );
                """,
                # Session tokens table
                """
                CREATE TABLE IF NOT EXISTS session_tokens (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    portal_name TEXT NOT NULL,
                    cookies_json TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT now(),
                    expires_at TIMESTAMPTZ NOT NULL,
                    UNIQUE (user_id, portal_name)
                );
                """,
                # User preferences table
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE UNIQUE,
                    preferred_roles TEXT,
                    preferred_locations TEXT,
                    salary_min INTEGER,
                    salary_max INTEGER,
                    job_type TEXT,
                    open_to_remote BOOLEAN DEFAULT true,
                    updated_at TIMESTAMPTZ DEFAULT now()
                );
                """,
            ]
            for sql in migrations:
                try:
                    await session.execute(text(sql))
                except Exception as e:
                    print(f"[WARN] Migration skipped: {e}")
            await session.commit()
        print("[OK] Schema migrations applied")
        # Keep-alive: ping Neon every 4 minutes so the connection pool never goes cold
        async def _keepalive():
            import asyncio as _asyncio
            while True:
                await _asyncio.sleep(240)
                try:
                    async with AsyncSessionLocal() as s:
                        await s.execute(text("SELECT 1"))
                except Exception:
                    pass
        import asyncio as _asyncio
        _asyncio.create_task(_keepalive())
        print("[OK] DB keep-alive started (240s interval)")

        # Fix existing resume_path values — scan RESUME_DIR and correct any stale/missing paths
        try:
            import os as _os
            from sqlalchemy import select as _select, update as _update
            from db.models import User as _User
            from api.routes.pipeline import RESUME_DIR as _RESUME_DIR

            # Build a map: user_id_prefix → absolute file path
            resume_map: dict[str, str] = {}
            if _os.path.isdir(_RESUME_DIR):
                for fname in _os.listdir(_RESUME_DIR):
                    # filenames are "{user_id}_resume.{ext}"
                    parts = fname.split("_resume.", 1)
                    if len(parts) == 2:
                        resume_map[parts[0]] = _os.path.join(_RESUME_DIR, fname)

            if resume_map:
                async with AsyncSessionLocal() as session:
                    users = (await session.execute(_select(_User))).scalars().all()
                    fixed = 0
                    for u in users:
                        uid = str(u.id)
                        correct_path = resume_map.get(uid)
                        if correct_path and u.resume_path != correct_path:
                            u.resume_path = correct_path
                            session.add(u)
                            fixed += 1
                    if fixed:
                        await session.commit()
                        print(f"[OK] Fixed resume_path for {fixed} user(s)")
                    else:
                        print("[OK] All resume_path values are up to date")
        except Exception as e:
            print(f"[WARN] resume_path fix skipped: {e}")

    except Exception as e:
        print(f"[WARN] Startup error: {e}")
    yield


app = FastAPI(title="Job Matching Agent API", version="1.0.0", lifespan=lifespan)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from api.routes.auth import router as auth_router
    app.include_router(auth_router)
    print("[OK] auth routes loaded")
except Exception:
    print("[FAIL] auth routes failed:")
    traceback.print_exc()

try:
    from api.routes.dashboard import router as dashboard_router
    app.include_router(dashboard_router)
    print("[OK] dashboard routes loaded")
except Exception:
    print("[FAIL] dashboard routes failed:")
    traceback.print_exc()

try:
    from api.routes.pipeline import router as pipeline_router
    app.include_router(pipeline_router)
    print("[OK] pipeline routes loaded")
except Exception:
    print("[FAIL] pipeline routes failed:")
    traceback.print_exc()


@app.get("/health")
async def health():
    return {"status": "ok"}
