"""STEP 5 — Find recruiter/contact emails for matched jobs."""
import re
import json
import asyncio
import os
import httpx
import dns.resolver
from agents import function_tool
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
SKIP_DOMAINS = {"example.", "sentry.", "placeholder", "domain.", "your@", "user@",
                "wixpress.", "cloudflare.", "google.", "facebook.", "w3.org",
                "schema.org", "png", "jpg", "svg"}

# Common recruiter email prefixes to try
RECRUITER_PREFIXES = ["careers", "jobs", "hiring", "hr", "recruit",
                      "talent", "apply", "work", "people"]


def _company_to_domain(company: str) -> str:
    """Best-effort domain from company name."""
    name = re.sub(r"[^a-z0-9 ]", "", company.lower().strip())
    words = name.split()
    stops = {"inc", "llc", "ltd", "co", "corp", "group", "solutions", "the",
             "technologies", "technology", "labs", "ai", "and", "of"}
    words = [w for w in words if w not in stops]
    base = words[0] if words else name.replace(" ", "")
    return f"{base}.com"


async def _mx_exists(domain: str) -> bool:
    try:
        loop = asyncio.get_event_loop()
        answers = await loop.run_in_executor(None, dns.resolver.resolve, domain, "MX")
        return len(answers) > 0
    except Exception:
        return False


async def _scrape_page_emails(client: httpx.AsyncClient, url: str) -> list[str]:
    """Scrape visible emails from a job listing page."""
    try:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        raw = list(set(EMAIL_RE.findall(soup.get_text())))
        return [e for e in raw
                if not any(s in e.lower() for s in SKIP_DOMAINS)
                and len(e) < 80]
    except Exception:
        return []


async def _hunter_search(client: httpx.AsyncClient, domain: str) -> list[str]:
    """Hunter.io domain search — returns emails if API key is configured."""
    key = os.getenv("HUNTER_API_KEY", "")
    if not key:
        return []
    try:
        resp = await client.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": key, "limit": 3},
            timeout=8,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [e["value"] for e in data.get("data", {}).get("emails", [])
                if e.get("value")][:3]
    except Exception:
        return []


async def _guess_emails(company: str) -> list[str]:
    """Generate plausible recruiter emails and return those with valid MX."""
    domain = _company_to_domain(company)
    if not await _mx_exists(domain):
        return []
    # Return the most common patterns — MX valid means domain exists
    return [f"{prefix}@{domain}" for prefix in RECRUITER_PREFIXES[:3]]


async def email_finder_impl(matched_jobs_json: str) -> str:
    raw = json.loads(matched_jobs_json)
    matched_jobs = raw.get("matched_jobs", []) if isinstance(raw, dict) else raw

    async def find_for_job(job: dict) -> dict:
        url = job.get("url", "")
        company = job.get("company", "")
        db_job_id = job.get("db_job_id", "")
        emails: list[str] = []

        async with httpx.AsyncClient(follow_redirects=True) as client:
            # 1. Scrape job listing page
            if url:
                page_emails = await _scrape_page_emails(client, url)
                emails.extend(page_emails)

            # 2. Hunter.io if key configured and nothing found yet
            if not emails and company:
                domain = _company_to_domain(company)
                hunter_emails = await _hunter_search(client, domain)
                emails.extend(hunter_emails)

        # 3. Guess common patterns if still nothing
        if not emails and company:
            guessed = await _guess_emails(company)
            emails.extend(guessed)

        # Deduplicate
        seen: set = set()
        unique = []
        for e in emails:
            if e not in seen:
                seen.add(e)
                unique.append(e)

        return {
            "job_title": job.get("title", ""),
            "company": company,
            "job_url": url,
            "db_job_id": db_job_id,
            "emails": unique[:5],
        }

    results = await asyncio.gather(*[find_for_job(j) for j in matched_jobs[:10]])
    return json.dumps({"success": True, "email_results": list(results)})


@function_tool
async def email_finder_tool(matched_jobs_json: str) -> str:
    """Find recruiter email addresses for matched jobs.
    Tries: page scraping → Hunter.io → common pattern guessing with MX validation.
    Returns JSON with email_results array.
    """
    return await email_finder_impl(matched_jobs_json=matched_jobs_json)
