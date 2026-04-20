"""user_preference_tool — Store and retrieve user job-search preferences.

Wraps the UserPreference ORM model.
Preferences are used to pre-fill pipeline fields and apply salary / job-type
filters automatically on each run — avoiding re-entry every session.
"""
import json
import uuid
from agents import function_tool
from sqlalchemy import select
from db.database import AsyncSessionLocal
from db.models import UserPreference


async def preference_get_impl(user_id: str) -> str:
    """Load the user's saved preferences."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            pref = (await session.execute(
                select(UserPreference).where(UserPreference.user_id == uid)
            )).scalar_one_or_none()

        if not pref:
            return json.dumps({
                "success":            True,
                "found":              False,
                "preferred_roles":    "",
                "preferred_locations": "",
                "salary_min":         None,
                "salary_max":         None,
                "job_type":           "full-time",
                "open_to_remote":     True,
            })

        return json.dumps({
            "success":             True,
            "found":               True,
            "preferred_roles":     pref.preferred_roles or "",
            "preferred_locations": pref.preferred_locations or "",
            "salary_min":          pref.salary_min,
            "salary_max":          pref.salary_max,
            "job_type":            pref.job_type or "full-time",
            "open_to_remote":      pref.open_to_remote,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


async def preference_set_impl(
    user_id: str,
    preferred_roles: str = "",
    preferred_locations: str = "",
    salary_min: int | None = None,
    salary_max: int | None = None,
    job_type: str = "full-time",
    open_to_remote: bool = True,
) -> str:
    """Save or update the user's preferences (upsert)."""
    uid = uuid.UUID(user_id)
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                pref = (await session.execute(
                    select(UserPreference).where(UserPreference.user_id == uid)
                )).scalar_one_or_none()

                if pref:
                    pref.preferred_roles     = preferred_roles
                    pref.preferred_locations = preferred_locations
                    pref.salary_min          = salary_min
                    pref.salary_max          = salary_max
                    pref.job_type            = job_type
                    pref.open_to_remote      = open_to_remote
                else:
                    pref = UserPreference(
                        id=uuid.uuid4(),
                        user_id=uid,
                        preferred_roles=preferred_roles,
                        preferred_locations=preferred_locations,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        job_type=job_type,
                        open_to_remote=open_to_remote,
                    )
                    session.add(pref)

        return json.dumps({"success": True, "message": "Preferences saved."})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@function_tool
async def user_preference_get_tool(user_id: str) -> str:
    """Load saved job-search preferences for a user.

    Returns preferred_roles, preferred_locations, salary_min/max,
    job_type (full-time | contract | part-time), open_to_remote.
    """
    return await preference_get_impl(user_id=user_id)


@function_tool
async def user_preference_set_tool(
    user_id: str,
    preferred_roles: str = "",
    preferred_locations: str = "",
    salary_min: int = 0,
    salary_max: int = 0,
    job_type: str = "full-time",
    open_to_remote: bool = True,
) -> str:
    """Save job-search preferences for a user (upsert).

    All fields are optional — only supply the ones you want to update.
    salary_min / salary_max: annual USD; 0 means no bound.
    """
    return await preference_set_impl(
        user_id=user_id,
        preferred_roles=preferred_roles,
        preferred_locations=preferred_locations,
        salary_min=salary_min or None,
        salary_max=salary_max or None,
        job_type=job_type,
        open_to_remote=open_to_remote,
    )
