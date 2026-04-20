"""job_expiry_checker_tool — Verify jobs are still active before applying.

Two-stage check:
  1. Date-based: posting > JOB_STALE_DAYS old → expired.
  2. URL-based: GET job URL; 404 or known "no longer available" phrase → expired.

Expired jobs are removed from the list, preventing wasted applications.
"""
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta

import httpx
from agents import function_tool

STALE_DAYS = int(os.getenv("JOB_STALE_DAYS", "30"))

_EXPIRED_PHRASES = [
    "no longer available",
    "position has been filled",
    "job has expired",
    "this job is no longer",
    "listing has expired",
    "job no longer exists",
    "this listing is closed",
    "position filled",
    "not accepting applications",
]


async def _is_job_active(url: str) -> bool:
    """Return False if URL 404s or contains an expiry phrase in first 3 KB."""
    if not url or not url.startswith("http"):
        return True  # No URL → assume active (don't drop unknown)
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 (compatible; JobChecker/1.0)"},
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return False
            snippet = resp.text[:3000].lower()
            if any(phrase in snippet for phrase in _EXPIRED_PHRASES):
                return False
    except Exception:
        pass  # Network error → don't drop the job
    return True


async def job_expiry_checker_impl(jobs_json: str) -> str:
    jobs = json.loads(jobs_json) if isinstance(jobs_json, str) else jobs_json
    if isinstance(jobs, dict):
        jobs = jobs.get("jobs", [])

    now = datetime.now(timezone.utc)
    semaphore = asyncio.Semaphore(5)  # max 5 concurrent URL checks

    async def check(job: dict) -> dict | None:
        async with semaphore:
            # Stage 1 — date check
            posted_str = job.get("date") or job.get("created_at") or ""
            if posted_str:
                try:
                    posted = datetime.fromisoformat(posted_str.replace("Z", "+00:00"))
                    if (now - posted).days > STALE_DAYS:
                        return None
                except Exception:
                    pass  # Unparseable date → skip date check

            # Stage 2 — URL check
            url = job.get("url") or job.get("job_url") or ""
            if url and not await _is_job_active(url):
                return None

            return job

    results = await asyncio.gather(*[check(j) for j in jobs])
    active   = [r for r in results if r is not None]
    expired  = len(jobs) - len(active)

    return json.dumps({
        "success":          True,
        "jobs":             active,
        "active_count":     len(active),
        "expired_removed":  expired,
    })


@function_tool
async def job_expiry_checker_tool(jobs_json: str) -> str:
    """Check each job URL and posting date to remove expired listings.

    Prevents wasting applications on positions that are no longer open.
    jobs_json: JSON array of job objects with optional url and date fields.
    """
    return await job_expiry_checker_impl(jobs_json=jobs_json)
