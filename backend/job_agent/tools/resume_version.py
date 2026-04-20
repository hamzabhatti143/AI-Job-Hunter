"""resume_version_tool — Version and manage multiple resume variants.

Stores references to resume versions in the resume_versions DB table.
Allows users to track which version they sent to which job and compare outcomes.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import text
from agents import function_tool
from db.database import AsyncSessionLocal

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS resume_versions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL DEFAULT 1,
    label          TEXT,
    file_path      TEXT NOT NULL,
    notes          TEXT,
    is_active      BOOLEAN DEFAULT true,
    created_at     TIMESTAMPTZ DEFAULT now()
);
"""


async def _ensure_table(session) -> None:
    await session.execute(text(_CREATE_SQL))


async def resume_version_save_impl(
    user_id: str,
    file_path: str,
    label: str = "",
    notes: str = "",
) -> str:
    """Register a new resume version for the user."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await _ensure_table(session)

                # Get current max version number
                result = await session.execute(text("""
                    SELECT COALESCE(MAX(version_number), 0) FROM resume_versions
                    WHERE user_id = :uid
                """), {"uid": uid})
                max_version = result.scalar() or 0

                new_version = max_version + 1
                await session.execute(text("""
                    INSERT INTO resume_versions
                        (id, user_id, version_number, label, file_path, notes)
                    VALUES
                        (gen_random_uuid(), :uid, :ver, :label, :path, :notes)
                """), {
                    "uid": uid, "ver": new_version,
                    "label": label or f"v{new_version}",
                    "path": file_path, "notes": notes,
                })

        return json.dumps({
            "success":        True,
            "version_number": new_version,
            "label":          label or f"v{new_version}",
            "file_path":      file_path,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


async def resume_version_list_impl(user_id: str) -> str:
    """List all resume versions for the user."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            await _ensure_table(session)
            result = await session.execute(text("""
                SELECT id, version_number, label, file_path, notes, is_active, created_at
                FROM resume_versions
                WHERE user_id = :uid
                ORDER BY version_number DESC
            """), {"uid": uid})
            rows = result.fetchall()

        return json.dumps({
            "success": True,
            "versions": [
                {
                    "id":             str(r.id),
                    "version_number": r.version_number,
                    "label":          r.label or f"v{r.version_number}",
                    "file_path":      r.file_path,
                    "notes":          r.notes or "",
                    "is_active":      r.is_active,
                    "created_at":     r.created_at.isoformat(),
                }
                for r in rows
            ],
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


async def resume_version_delete_impl(user_id: str, version_id: str) -> str:
    """Remove a resume version record (does not delete the file)."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await _ensure_table(session)
                await session.execute(text("""
                    DELETE FROM resume_versions
                    WHERE id = :vid AND user_id = :uid
                """), {"vid": uuid.UUID(version_id), "uid": uid})
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def resume_version_tool(
    user_id: str,
    file_path: str,
    label: str = "",
    notes: str = "",
) -> str:
    """Register a new resume version in the user's version history.

    label: short name like 'Frontend v2' or 'Tailored for startups'.
    notes: optional context (e.g. 'added Tailwind, removed PHP').
    """
    return await resume_version_save_impl(
        user_id=user_id, file_path=file_path, label=label, notes=notes
    )
