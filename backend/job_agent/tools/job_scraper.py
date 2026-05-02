"""STEP 3 — Search jobs by querying Google directly (position + location).

Flow:
  1. Build query  → "{position} jobs {location}"
  2. SerpAPI Google Jobs engine → structured job cards
  3. SerpAPI organic Google search → extra listing URLs
  4. Deduplicate + clean → return unified job list

Company name comes from the job card or is inferred from the posting URL domain.
Email discovery and company verification happen downstream in company_finder.py.
"""
import json
import re
import asyncio
import os
import httpx
from agents import function_tool
from urllib.parse import urlparse

# ── Remote detection (imported by pipeline.py) ───────────────────────────────

_REMOTE_TERMS = frozenset([
    "remote", "wfh", "work from home", "work-from-home", "anywhere",
    "worldwide", "global", "distributed", "fully remote", "no office",
])

_REMOTE_FILTER_TERMS = frozenset([
    "remote", "worldwide", "anywhere", "global", "wfh",
    "work from home", "distributed", "fully remote",
])


def _is_remote_input(location: str) -> bool:
    return location.strip().lower() in _REMOTE_TERMS


# ── Company name cleaning (also imported by job_matcher.py) ──────────────────

_BAD_COMPANY_NAMES = {
    "", "n/a", "na", "unknown", "various", "multiple", "confidential",
    "anonymous", "undisclosed", "not specified", "not disclosed",
    "your organization", "your company", "your organisation",
    "organization", "organisation", "company", "employer",
    "hiring company", "hiring organization", "hiring organisation",
    "client", "our client", "our company", "our organization",
    "a client", "leading company", "top company", "global company",
    "mnc", "mnc company", "acca listed",
}


def _clean_company(name: str) -> str:
    """Return cleaned company name, or empty string if it's a known placeholder."""
    if not name:
        return ""
    cleaned = name.strip()
    if cleaned.lower() in _BAD_COMPANY_NAMES:
        return ""
    cleaned = re.sub(r'\s*[|·•\-–—]\s*$', '', cleaned).strip()
    return cleaned if len(cleaned) >= 2 else ""


# ── Helpers ───────────────────────────────────────────────────────────────────

_AGGREGATOR_DOMAINS = {
    "linkedin.com", "indeed.com", "glassdoor.com", "monster.com",
    "ziprecruiter.com", "simplyhired.com", "careerbuilder.com",
    "dice.com", "jobstreet.com", "naukri.com", "bayt.com",
    "rozee.pk", "brightspyre.com", "wuzzuf.net", "seek.com.au",
    "reed.co.uk", "totaljobs.com", "cwjobs.co.uk", "jobs.google.com",
    "google.com",
}


def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def _company_from_domain(domain: str) -> str:
    """Best-effort company name from a domain like 'careers.stripe.com' → 'Stripe'."""
    domain = re.sub(r"^(careers|jobs|apply|talent|work|hiring|join)\.", "", domain)
    name = domain.split(".")[0]
    return name.replace("-", " ").title()


def _best_url(job: dict) -> str:
    """
    From a Google Jobs result, prefer the company's own career page URL
    over aggregator links (LinkedIn, Indeed, etc.).
    Falls back to the first available apply link.
    """
    apply_opts = job.get("apply_options") or []
    if not isinstance(apply_opts, list):
        apply_opts = []

    # Separate direct company links from aggregator links
    direct, aggregator = [], []
    for opt in apply_opts:
        if not isinstance(opt, dict):
            continue
        link = opt.get("link") or ""
        if not link:
            continue
        dom = _domain_from_url(link)
        if any(agg in dom for agg in _AGGREGATOR_DOMAINS):
            aggregator.append(link)
        else:
            direct.append(link)

    # Prefer direct company link; fall back to aggregator
    if direct:
        return direct[0]
    if aggregator:
        return aggregator[0]
    return ""


# ── Google Jobs via SerpAPI ───────────────────────────────────────────────────

async def _fetch_google_jobs(client: httpx.AsyncClient, query: str, api_key: str, date_posted: str = "week") -> list[dict]:
    """Call SerpAPI google_jobs engine. Returns structured job cards."""
    jobs: list[dict] = []
    try:
        r = await client.get(
            "https://serpapi.com/search",
            params={"engine": "google_jobs", "q": query, "num": "50", "api_key": api_key, "date_posted": date_posted},
            timeout=30,
        )
        if r.status_code != 200:
            return jobs

        for item in (r.json().get("jobs_results") or []):
            url = _best_url(item)
            company_raw = item.get("company_name", "")
            company     = _clean_company(company_raw)

            # Infer company from URL if card didn't give us one
            if not company and url:
                dom = _domain_from_url(url)
                if dom and not any(agg in dom for agg in _AGGREGATOR_DOMAINS):
                    company = _company_from_domain(dom)

            extensions = item.get("job_highlights") or []
            tags = []
            for block in extensions:
                tags.extend(block.get("items") or [])

            jobs.append({
                "title":       item.get("title", ""),
                "company":     company,
                "location":    item.get("location", ""),
                "url":         url,
                "description": (item.get("description") or "")[:600],
                "tags":        tags[:10],
                "source":      "google_jobs",
            })
    except Exception:
        pass
    return jobs


# ── Organic Google search via SerpAPI ─────────────────────────────────────────

async def _fetch_google_organic(client: httpx.AsyncClient, query: str, api_key: str, tbs: str = "qdr:w") -> list[dict]:
    """Fallback: regular Google organic results for job-related pages."""
    jobs: list[dict] = []
    try:
        params: dict = {"engine": "google", "q": query, "num": "30", "api_key": api_key}
        if tbs:
            params["tbs"] = tbs
        r = await client.get(
            "https://serpapi.com/search",
            params=params,
            timeout=30,
        )
        if r.status_code != 200:
            return jobs

        for res in (r.json().get("organic_results") or []):
            url = res.get("link", "")
            if not url:
                continue
            dom           = _domain_from_url(url)
            is_aggregator = any(agg in dom for agg in _AGGREGATOR_DOMAINS)
            company       = _company_from_domain(dom) if dom and not is_aggregator else ""

            # Try to extract job title from the page title
            title = res.get("title", "")
            # Remove site name suffix: "Software Engineer | Google" → "Software Engineer"
            title = re.split(r"\s*[\|·—–]\s*", title)[0].strip()

            jobs.append({
                "title":       title,
                "company":     _clean_company(company),
                "location":    "",
                "url":         url,
                "description": res.get("snippet", ""),
                "tags":        [],
                "source":      "google_search",
            })
    except Exception:
        pass
    return jobs


# ── Main implementation ───────────────────────────────────────────────────────

import datetime as _dt

# Query rotation templates — varied each call so repeated runs return fresh results
_QUERY_TEMPLATES = [
    "{position} jobs {loc}",
    "{position} vacancy {loc}",
    "{position} hiring {loc}",
    "{position} job opening {loc}",
    "{position} position {loc} 2025",
]


async def job_scraper_impl(skills_json: str, location: str, role_preference: str) -> str:
    api_key = os.getenv("SERPAPI_KEY") or os.getenv("SERP_API_KEY", "")

    if not api_key:
        return json.dumps({
            "success": False,
            "jobs": [],
            "count": 0,
            "error": "SERPAPI_KEY is not configured. Set it in backend/.env to enable job search.",
        })

    position = role_preference.strip()
    loc      = location.strip()

    minute = _dt.datetime.now().minute

    # All 5 query templates — run them all for maximum coverage
    gj_queries = list(dict.fromkeys(
        t.format(position=position, loc=loc).strip()
        for t in _QUERY_TEMPLATES
    ))

    # Two organic queries with different phrasings
    organic_queries = [
        (f"{_QUERY_TEMPLATES[minute % 5].format(position=position, loc=loc).strip()} "
         f"(job OR vacancy OR opening OR \"apply now\" OR careers)"),
        f'"{position}" jobs {loc} 2025',
    ]

    # ── Dual-key dedup: URL primary, title+company fingerprint secondary ─────
    seen_urls:         set[str] = set()
    seen_fingerprints: set[str] = set()
    all_jobs:          list[dict] = []

    def _fp(job: dict) -> str:
        t = re.sub(r'\s+', ' ', (job.get("title") or "").lower().strip())[:70]
        c = (job.get("company") or "").lower().strip()[:40]
        return f"{t}|{c}"

    def _add(job_list: list[dict]):
        for j in job_list:
            url = (j.get("url") or "").strip()
            fp  = _fp(j)
            if url and url in seen_urls:
                continue
            if fp and fp != "|" and fp in seen_fingerprints:
                continue
            if url:
                seen_urls.add(url)
            if fp and fp != "|":
                seen_fingerprints.add(fp)
            all_jobs.append(j)

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"},
        follow_redirects=True,
    ) as client:
        # Stagger Google Jobs calls by 0.2s to avoid SerpAPI rate-limiting
        gj_raw = []
        for i, q in enumerate(gj_queries):
            if i > 0:
                await asyncio.sleep(0.2)
            gj_raw.append(asyncio.ensure_future(_fetch_google_jobs(client, q, api_key)))

        org_futures = [
            asyncio.ensure_future(_fetch_google_organic(client, q, api_key))
            for q in organic_queries
        ]

        gj_results  = await asyncio.gather(*gj_raw,     return_exceptions=True)
        org_results = await asyncio.gather(*org_futures, return_exceptions=True)

    google_jobs = [j for r in gj_results  if isinstance(r, list) for j in r]
    organic     = [j for r in org_results if isinstance(r, list) for j in r]

    _add(google_jobs)
    _add(organic)

    # ── If still fewer than 40 unique jobs, extend date range to 1 month ────
    # (weekly filter can be sparse for smaller markets)
    if len(all_jobs) < 40:
        extra_queries = [
            _QUERY_TEMPLATES[(minute + 1) % 5].format(position=position, loc=loc).strip(),
            _QUERY_TEMPLATES[(minute + 3) % 5].format(position=position, loc=loc).strip(),
        ]
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"},
            follow_redirects=True,
        ) as client:
            extra_gj  = await asyncio.gather(
                *[_fetch_google_jobs(client, q, api_key, date_posted="month") for q in extra_queries],
                return_exceptions=True,
            )
            extra_org = await _fetch_google_organic(
                client,
                f"{position} jobs {loc}",
                api_key,
                tbs="qdr:m",
            )
        for r in extra_gj:
            if isinstance(r, list):
                _add(r)
        if isinstance(extra_org, list):
            _add(extra_org)

    return json.dumps({
        "success": True,
        "jobs":    all_jobs[:200],
        "count":   len(all_jobs[:200]),
        "query":   gj_queries[0],
    })


@function_tool
async def job_scraper_tool(skills_json: str, location: str, role_preference: str) -> str:
    """
    Search for jobs by querying Google directly with the user's position and location.
    Returns job listings found across Google Jobs + organic Google results.
    Requires: SERPAPI_KEY in environment.
    """
    return await job_scraper_impl(
        skills_json=skills_json,
        location=location,
        role_preference=role_preference,
    )
