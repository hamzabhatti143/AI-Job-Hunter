"""job_deduplication_tool — Remove duplicate job listings across sources.

Compares job_title + company + location hash to eliminate duplicates.
Handles the same job appearing on LinkedIn, Indeed, Glassdoor simultaneously.
"""
import hashlib
import json
from agents import function_tool


def _job_key(job: dict) -> str:
    """Create a normalized deduplication fingerprint."""
    title    = (job.get("title") or "").lower().strip()
    company  = (job.get("company") or "").lower().strip()
    location = (job.get("location") or "").lower().strip()
    # Normalise common abbreviations so "Remote" and "remote" collapse
    combined = f"{title}|{company}|{location}"
    return hashlib.md5(combined.encode()).hexdigest()


async def job_deduplication_impl(jobs_json: str) -> str:
    jobs = json.loads(jobs_json) if isinstance(jobs_json, str) else jobs_json
    if isinstance(jobs, dict):
        jobs = jobs.get("jobs", [])

    seen: set[str]   = set()
    unique: list[dict] = []
    duplicates = 0

    for job in jobs:
        key = _job_key(job)
        if key not in seen:
            seen.add(key)
            unique.append(job)
        else:
            duplicates += 1

    return json.dumps({
        "success":           True,
        "jobs":              unique,
        "original_count":   len(jobs),
        "unique_count":     len(unique),
        "duplicates_removed": duplicates,
    })


@function_tool
async def job_deduplication_tool(jobs_json: str) -> str:
    """Remove duplicate job listings using title+company+location fingerprint.

    Returns deduplicated list — same job appearing on multiple boards is kept once.
    jobs_json: JSON array of job objects.
    """
    return await job_deduplication_impl(jobs_json=jobs_json)
