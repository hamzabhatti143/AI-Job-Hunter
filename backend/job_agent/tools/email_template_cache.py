"""email_template_cache_tool — Cache generated email templates per job type.

Keyed on (normalised job title category, top-3 skills).
Only personalisation fields (company name, recruiter name, etc.) change per send.
Reduces Gemini/OpenAI token consumption significantly on repeat runs.

Cache is in-process memory with a configurable TTL (default 24 h).
"""
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta

from agents import function_tool

CACHE_TTL_HOURS = int(os.getenv("EMAIL_TEMPLATE_CACHE_TTL_HOURS", "24"))

# {cache_key: {"template": str, "cached_at": datetime}}
_cache: dict[str, dict] = {}


def _make_key(job_title: str, skills: list[str]) -> str:
    title_norm  = " ".join(job_title.lower().split()[:4])          # first 4 words of title
    skills_norm = ",".join(sorted(s.lower() for s in skills[:3]))  # top 3 skills, sorted
    return hashlib.md5(f"{title_norm}|{skills_norm}".encode()).hexdigest()


def _is_valid(entry: dict) -> bool:
    age = datetime.now(timezone.utc) - entry["cached_at"]
    return age <= timedelta(hours=CACHE_TTL_HOURS)


async def cache_get_impl(job_title: str, skills_json: str) -> str:
    """Look up cached template. Returns hit=True + template, or hit=False."""
    skills = json.loads(skills_json) if isinstance(skills_json, str) else skills_json
    key    = _make_key(job_title, skills)
    entry  = _cache.get(key)

    if not entry:
        return json.dumps({"hit": False, "key": key})

    if not _is_valid(entry):
        del _cache[key]
        return json.dumps({"hit": False, "key": key, "reason": "expired"})

    return json.dumps({
        "hit":       True,
        "key":       key,
        "template":  entry["template"],
        "cached_at": entry["cached_at"].isoformat(),
    })


async def cache_set_impl(job_title: str, skills_json: str, template: str) -> str:
    """Store a generated template in the cache."""
    skills = json.loads(skills_json) if isinstance(skills_json, str) else skills_json
    key    = _make_key(job_title, skills)
    _cache[key] = {
        "template":  template,
        "cached_at": datetime.now(timezone.utc),
    }
    return json.dumps({"success": True, "key": key, "cache_size": len(_cache)})


async def cache_stats_impl() -> str:
    """Return cache occupancy stats."""
    now   = datetime.now(timezone.utc)
    valid = sum(1 for v in _cache.values() if _is_valid(v))
    return json.dumps({
        "total_entries": len(_cache),
        "valid_entries": valid,
        "stale_entries": len(_cache) - valid,
        "ttl_hours":     CACHE_TTL_HOURS,
    })


async def cache_clear_impl() -> str:
    """Evict all stale entries."""
    before = len(_cache)
    stale  = [k for k, v in _cache.items() if not _is_valid(v)]
    for k in stale:
        del _cache[k]
    return json.dumps({"evicted": len(stale), "remaining": len(_cache), "before": before})


@function_tool
async def email_template_cache_get(job_title: str, skills_json: str) -> str:
    """Retrieve a cached email template for a job title + skills combination.

    Returns hit=True and template string if found and not expired.
    skills_json: JSON array of skill strings.
    """
    return await cache_get_impl(job_title=job_title, skills_json=skills_json)


@function_tool
async def email_template_cache_set(job_title: str, skills_json: str, template: str) -> str:
    """Store a generated email template in the cache for future reuse.

    skills_json: JSON array of skill strings.
    template: the full email body template to cache.
    """
    return await cache_set_impl(job_title=job_title, skills_json=skills_json, template=template)
