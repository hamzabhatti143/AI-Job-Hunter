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
        from db.database import verify_db_connection
        await verify_db_connection()
        print("[OK] Database connected")
    except Exception as e:
        print(f"[WARN] Database connection failed: {e}")
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
