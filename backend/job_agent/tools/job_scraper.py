"""STEP 3 — Search jobs from multiple sources using role, skills and location from the resume."""
import json
import asyncio
import httpx
from agents import function_tool


def _to_tag(s: str) -> str:
    return s.lower().strip().replace(" ", "-").replace(".", "-").replace("/", "-")


def _build_search_terms(role: str, skills: list[str]) -> list[str]:
    """
    Build ordered search terms directly from the role and top skills.
    No hardcoded mapping — uses exactly what was extracted from the resume.
    """
    terms: list[str] = []

    # Full role as-is (e.g. "Frontend Developer", "Data Scientist")
    if role:
        terms.append(role.strip())

    # Individual meaningful words from the role (len > 3, not stopwords)
    stopwords = {"and", "the", "for", "with", "from", "that", "this", "are", "was"}
    if role:
        for word in role.split():
            w = word.strip().lower()
            if len(w) > 3 and w not in stopwords and w not in [t.lower() for t in terms]:
                terms.append(w)

    # Top 4 skills as additional search terms
    for skill in skills[:4]:
        sk = skill.strip()
        if sk and sk.lower() not in [t.lower() for t in terms]:
            terms.append(sk)

    return terms


async def _fetch_remoteok(client: httpx.AsyncClient, terms: list[str]) -> list[dict]:
    """RemoteOK — remote jobs searched by tag."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    jobs: list[dict] = []
    seen: set[str] = set()

    for term in terms:
        if len(jobs) >= 20:
            break
        tag = _to_tag(term)
        try:
            url = f"https://remoteok.com/api?tag={tag}" if tag else "https://remoteok.com/api"
            resp = await client.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict) or not item.get("position"):
                    continue
                job_url = item.get("url") or f"https://remoteok.com/l/{item.get('id','')}"
                if job_url in seen:
                    continue
                seen.add(job_url)
                jobs.append({
                    "title":       item.get("position", ""),
                    "company":     item.get("company", ""),
                    "location":    item.get("location") or "Remote",
                    "url":         job_url,
                    "description": (item.get("description") or "")[:2000],
                    "tags":        item.get("tags") or [],
                    "source":      "remoteok",
                })
        except Exception:
            continue

    return jobs


async def _fetch_remotive(client: httpx.AsyncClient, role: str, skills: list[str]) -> list[dict]:
    """Remotive — remote jobs searched by role or top skill."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    jobs: list[dict] = []
    seen: set[str] = set()

    # Try role first, then each top skill
    search_terms = [role] + [s for s in skills[:3] if s.lower() not in role.lower()]
    for term in search_terms:
        if not term:
            continue
        try:
            resp = await client.get(
                "https://remotive.com/api/remote-jobs",
                params={"search": term, "limit": 15},
                headers=headers,
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            for item in (resp.json().get("jobs") or []):
                if not isinstance(item, dict):
                    continue
                job_url = item.get("url", "")
                if not job_url or job_url in seen:
                    continue
                seen.add(job_url)
                jobs.append({
                    "title":       item.get("title", ""),
                    "company":     item.get("company_name", ""),
                    "location":    item.get("candidate_required_location") or "Remote",
                    "url":         job_url,
                    "description": (item.get("description") or "")[:2000],
                    "tags":        item.get("tags") if isinstance(item.get("tags"), list) else [],
                    "source":      "remotive",
                })
        except Exception:
            continue

    return jobs


async def _fetch_arbeitnow(client: httpx.AsyncClient, role: str, location: str) -> list[dict]:
    """Arbeitnow — international job board, supports location search."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    jobs: list[dict] = []
    seen: set[str] = set()

    # Search with role + location, then role alone
    searches = [
        {"search": role, "location": location},
        {"search": role},
    ]
    if location.lower() not in ("remote", ""):
        searches.append({"search": role, "location": "remote"})

    for params in searches:
        if not params.get("search"):
            continue
        try:
            resp = await client.get(
                "https://www.arbeitnow.com/api/job-board-api",
                params=params,
                headers=headers,
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            for item in (resp.json().get("data") or []):
                if not isinstance(item, dict):
                    continue
                job_url = item.get("url", "")
                if not job_url or job_url in seen:
                    continue
                seen.add(job_url)
                jobs.append({
                    "title":       item.get("title", ""),
                    "company":     item.get("company_name", ""),
                    "location":    item.get("location") or location or "Remote",
                    "url":         job_url,
                    "description": (item.get("description") or "")[:2000],
                    "tags":        item.get("tags") or [],
                    "source":      "arbeitnow",
                })
        except Exception:
            continue

    return jobs


async def _fetch_findwork(client: httpx.AsyncClient, role: str, location: str) -> list[dict]:
    """Findwork.dev — supports role + location search."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    jobs: list[dict] = []
    seen: set[str] = set()

    try:
        params: dict = {"search": role, "page": 1}
        if location and location.lower() != "remote":
            params["location"] = location
        resp = await client.get(
            "https://findwork.dev/api/jobs/",
            params=params,
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            for item in (resp.json().get("results") or []):
                if not isinstance(item, dict):
                    continue
                job_url = item.get("url", "")
                if not job_url or job_url in seen:
                    continue
                seen.add(job_url)
                jobs.append({
                    "title":       item.get("role", ""),
                    "company":     item.get("company_name", ""),
                    "location":    item.get("location") or location or "Remote",
                    "url":         job_url,
                    "description": (item.get("text") or "")[:2000],
                    "tags":        item.get("keywords") or [],
                    "source":      "findwork",
                })
    except Exception:
        pass

    return jobs


async def _fetch_jobicy(client: httpx.AsyncClient, role: str, location: str) -> list[dict]:
    """Jobicy — global job board with onsite, hybrid and remote jobs. Supports geo filter."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    jobs: list[dict] = []
    seen: set[str] = set()

    # Convert location to a geo slug (first word, lowercase)
    geo = location.strip().split(",")[0].strip().lower().replace(" ", "-") if location else ""

    # Try with geo filter, then without
    param_sets = []
    if geo and geo not in ("remote", "anywhere", "worldwide"):
        param_sets.append({"count": 50, "geo": geo, "tag": _to_tag(role)})
        param_sets.append({"count": 50, "tag": _to_tag(role)})
    else:
        param_sets.append({"count": 50, "tag": _to_tag(role)})

    for params in param_sets:
        try:
            resp = await client.get(
                "https://jobicy.com/api/v0/jobs",
                params=params,
                headers=headers,
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            for item in (resp.json().get("jobs") or []):
                if not isinstance(item, dict):
                    continue
                job_url = item.get("jobExcerptLink") or item.get("jobGeo", "")
                if not job_url or job_url in seen:
                    continue
                seen.add(job_url)
                jobs.append({
                    "title":       item.get("jobTitle", ""),
                    "company":     item.get("companyName", ""),
                    "location":    item.get("jobGeo") or item.get("jobRegion") or location or "Remote",
                    "url":         job_url,
                    "description": (item.get("jobDescription") or "")[:2000],
                    "tags":        item.get("jobIndustry") or [],
                    "source":      "jobicy",
                })
        except Exception:
            continue

    return jobs


async def _fetch_themuse(client: httpx.AsyncClient, role: str, location: str) -> list[dict]:
    """The Muse — global job board with location support, includes onsite and hybrid."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    jobs: list[dict] = []
    seen: set[str] = set()

    params: dict = {"page": 0, "descending": "true"}
    # Map role to category
    role_lower = role.lower()
    if any(w in role_lower for w in ["frontend", "backend", "fullstack", "software", "developer", "engineer", "web"]):
        params["category"] = "Software Engineer"
    elif "data" in role_lower:
        params["category"] = "Data Science"
    elif "design" in role_lower:
        params["category"] = "Design & UX"
    elif "devops" in role_lower or "cloud" in role_lower:
        params["category"] = "IT"
    else:
        params["category"] = "Software Engineer"

    if location and location.lower() not in ("remote", "anywhere", "worldwide"):
        params["location"] = location.split(",")[0].strip()

    try:
        resp = await client.get(
            "https://www.themuse.com/api/public/jobs",
            params=params,
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            for item in (resp.json().get("results") or []):
                if not isinstance(item, dict):
                    continue
                job_url = item.get("refs", {}).get("landing_page", "")
                if not job_url or job_url in seen:
                    continue
                seen.add(job_url)
                locs = item.get("locations") or []
                loc_str = ", ".join(l.get("name", "") for l in locs if l.get("name")) or location or "Remote"
                jobs.append({
                    "title":       item.get("name", ""),
                    "company":     (item.get("company") or {}).get("name", ""),
                    "location":    loc_str,
                    "url":         job_url,
                    "description": (item.get("contents") or "")[:2000],
                    "tags":        [item.get("category", {}).get("name", "")] if item.get("category") else [],
                    "source":      "themuse",
                })
    except Exception:
        pass

    return jobs


async def job_scraper_impl(skills_json: str, location: str, role_preference: str) -> str:
    """
    Search jobs from 6 sources in parallel.
    Each source is searched both with the user's location (for local/onsite results)
    AND without location (for worldwide/remote results) — combined and deduplicated.
    The matcher then scores each job based on relevance.
    """
    skills: list[str] = json.loads(skills_json) if skills_json else []
    search_terms = _build_search_terms(role_preference, skills)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        results = await asyncio.gather(
            # Remote-only sources — always worldwide
            _fetch_remoteok(client, search_terms),
            _fetch_remotive(client, role_preference, skills),
            # Location-aware sources — searched twice: with location AND worldwide
            _fetch_arbeitnow(client, role_preference, location),
            _fetch_arbeitnow(client, role_preference, ""),          # worldwide
            _fetch_findwork(client, role_preference, location),
            _fetch_findwork(client, role_preference, ""),           # worldwide
            _fetch_jobicy(client, role_preference, location),
            _fetch_jobicy(client, role_preference, ""),             # worldwide
            _fetch_themuse(client, role_preference, location),
            _fetch_themuse(client, role_preference, ""),            # worldwide
            return_exceptions=True,
        )

    # Merge and deduplicate by URL
    all_jobs: list[dict] = []
    seen_urls: set[str] = set()
    for result in results:
        if isinstance(result, list):
            for job in result:
                url = job.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_jobs.append(job)

    return json.dumps({
        "success": True,
        "jobs": all_jobs[:100],
        "count": len(all_jobs[:100]),
    })


@function_tool
async def job_scraper_tool(skills_json: str, location: str, role_preference: str) -> str:
    """
    Search job listings using the role and location extracted from the resume.
    Searches RemoteOK, Remotive, Arbeitnow, Findwork, Jobicy, and The Muse in parallel.
    Uses exactly the role and location provided — no assumptions.
    """
    return await job_scraper_impl(
        skills_json=skills_json,
        location=location,
        role_preference=role_preference,
    )
