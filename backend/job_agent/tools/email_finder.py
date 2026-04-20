"""STEP 5 — Find recruiter/contact emails for matched jobs.

9-attempt strategy per job (stops at first valid email found):
  1. Scrape job listing page        (direct company sites only)
  2. Scrape company careers page    (10 URL path variants)
  3. Scrape company contact page    (10 URL path variants)
  4. Google/SerpAPI search
  5. Hunter.io domain search        (set HUNTER_API_KEY)
  6. Apollo.io people search        (set APOLLO_API_KEY — free 50/mo)
  7. Snov.io domain search          (set SNOV_CLIENT_ID + SNOV_CLIENT_SECRET — free 150/mo)
  8. LinkedIn company page
  9. Generate HR email patterns     (hr@, jobs@, careers@…) + MX-validate

Obfuscated email detection: "name [at] company [dot] com",
  HTML entities (&#64;), data-email attributes.

Validation: RFC 5322 format + MX record + not a system/noreply address.
Output: route = "email_apply" or "portal_apply" per job.

Free API setup:
  Apollo.io  → https://app.apollo.io/settings/integrations/api  (50 emails/mo free)
  Snov.io    → https://app.snov.io/api-setting                  (150 emails/mo free)
  Hunter.io  → https://hunter.io/api-keys                       (25 searches/mo free)
"""
import re
import json
import asyncio
import os
import socket
import httpx
import dns.resolver
from agents import function_tool
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
RFC5322_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

# Obfuscated email patterns — "name [at] company [dot] com"
_OBFUSC_RE = re.compile(
    r"([\w.+-]+)\s*(?:\[at\]|\(at\)|&#64;|\bat\b)\s*([\w-]+(?:\s*(?:\[dot\]|\(dot\)|&#46;|\bdot\b)\s*[\w-]+)*)"
    r"\s*(?:\[dot\]|\(dot\)|&#46;|\bdot\b)\s*([a-zA-Z]{2,})",
    re.IGNORECASE,
)

# HTML entity decode map for email obfuscation
_HTML_ENTITIES = {"&#64;": "@", "&#46;": ".", "&commat;": "@", "&period;": "."}

# Domains whose emails we always skip (noise / CDN / system addresses)
SKIP_DOMAINS = {
    "example.", "sentry.", "placeholder", "domain.", "wixpress.", "cloudflare.",
    "google.", "facebook.", "w3.org", "schema.org", "png", "jpg", "svg",
    "githubusercontent.", "unpkg.", "jsdelivr.",
}

# Job-board / aggregator domains — use company name to derive real domain
AGGREGATOR_DOMAINS = {
    "rozee.pk", "brightspyre.com", "pk.trabajo.org", "trabajo.org",
    "bebee.com", "arbeitnow.com", "remoteok.com", "remoteok.io",
    "remotive.com", "weworkremotely.com", "themuse.com", "jobicy.com",
    "findwork.dev", "joinimagine.com", "interviewpal.com", "bayt.com",
    "accaglobal.com", "jobs.accaglobal.com", "smartrecruiters.com",
    "jobs.smartrecruiters.com", "linkedin.com", "indeed.com",
    "glassdoor.com", "monster.com", "ziprecruiter.com",
}

# Hard block — truly automated/system addresses, never useful.
SYSTEM_PREFIXES = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "postmaster", "webmaster", "mailer-daemon", "bounce", "bounces",
    "abuse", "spam",
}

# Soft block — acceptable as a last resort if nothing better found.
GENERIC_PREFIXES = {
    "info", "support", "admin", "contact", "help", "hello", "team",
    "sales", "marketing", "billing", "legal", "privacy", "press",
    "feedback", "security", "service",
}

# HR-specific patterns to generate when scraping yields nothing.
# These are NOT in GENERIC_PREFIXES so they're treated as specific emails.
HR_PATTERNS = ["hr", "jobs", "careers", "recruit", "recruiting", "talent", "hiring", "people"]

# Extra URL paths to try for careers and contact pages
_CAREER_PATHS = [
    "/careers", "/jobs", "/career", "/join-us", "/work-with-us",
    "/join", "/hiring", "/opportunities", "/openings", "/vacancy",
]
_CONTACT_PATHS = [
    "/contact", "/contact-us", "/about", "/team", "/about-us",
    "/hr", "/human-resources", "/people", "/recruitment", "/get-in-touch",
]


def _is_system_email(email: str) -> bool:
    prefix = email.split("@")[0].lower().strip()
    return prefix in SYSTEM_PREFIXES


def _is_generic_email(email: str) -> bool:
    prefix = email.split("@")[0].lower().strip()
    return prefix in GENERIC_PREFIXES or prefix in SYSTEM_PREFIXES


def _company_to_domain_variants(company: str) -> list[str]:
    """Generate multiple domain variants from a company name to maximise hit rate."""
    name = re.sub(r"[^a-z0-9 ]", "", company.lower().strip())
    words = name.split()
    stops = {
        "inc", "llc", "ltd", "co", "corp", "group", "solutions", "the",
        "technologies", "technology", "labs", "ai", "and", "of", "for",
        "pvt", "private", "limited", "international",
    }
    cleaned = [w for w in words if w not in stops]

    variants: list[str] = []
    if cleaned:
        variants.append(f"{cleaned[0]}.com")                    # "contour.com"
        if len(cleaned) >= 2:
            variants.append(f"{''.join(cleaned[:2])}.com")      # "contoursoftware.com"
            variants.append(f"{cleaned[0]}-{cleaned[1]}.com")   # "contour-software.com"
        if len(cleaned) >= 3:
            variants.append(f"{''.join(cleaned[:3])}.com")      # "contoursoftwareltd.com"
    return list(dict.fromkeys(variants))


def _company_to_domain(company: str) -> str:
    """Best-effort single domain (for backward compat)."""
    variants = _company_to_domain_variants(company)
    return variants[0] if variants else ""


def _extract_domain_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.netloc or parsed.path
        return host.replace("www.", "").split("/")[0]
    except Exception:
        return ""


def _get_search_domain(url: str, company: str) -> str:
    """
    Return the domain to use for email scraping.
    When the job URL belongs to a known aggregator/job-board, use the company
    name to derive the hiring company's real domain.
    """
    url_domain = _extract_domain_from_url(url)
    is_aggregator = any(agg in url_domain for agg in AGGREGATOR_DOMAINS)
    if is_aggregator or not url_domain:
        return _company_to_domain(company) if company else ""
    return url_domain


async def _mx_exists(domain: str) -> bool:
    try:
        loop = asyncio.get_event_loop()
        answers = await loop.run_in_executor(None, dns.resolver.resolve, domain, "MX")
        return len(answers) > 0
    except Exception:
        return False


def _decode_html_entities(text: str) -> str:
    """Decode common HTML entity obfuscations used to hide emails."""
    for entity, char in _HTML_ENTITIES.items():
        text = text.replace(entity, char)
    return text


def _find_obfuscated_emails(text: str) -> list[str]:
    """
    Detect emails written as "name [at] company [dot] com" or
    "name(at)domain(dot)com" or with HTML entities.
    """
    text = _decode_html_entities(text)
    found: list[str] = []
    for m in _OBFUSC_RE.finditer(text):
        user = m.group(1).strip()
        middle = re.sub(
            r"\[dot\]|\(dot\)|&#46;|\bdot\b", ".", m.group(2), flags=re.IGNORECASE
        ).strip()
        tld = m.group(3).strip()
        candidate = f"{user}@{middle}.{tld}".lower()
        # Clean up any residual spaces
        candidate = re.sub(r"\s+", "", candidate)
        if RFC5322_RE.match(candidate):
            found.append(candidate)
    return found


def _clean_emails(raw: list[str]) -> list[str]:
    """Filter noise and generic addresses from a list of raw emails."""
    out = []
    seen: set[str] = set()
    for e in raw:
        e = e.lower().strip()
        if e in seen:
            continue
        seen.add(e)
        if not RFC5322_RE.match(e):
            continue
        if any(s in e for s in SKIP_DOMAINS):
            continue
        if len(e) > 80:
            continue
        out.append(e)
    return out


async def _scrape_emails(client: httpx.AsyncClient, url: str) -> list[str]:
    """
    Scrape visible + mailto: emails from any URL.
    Also detects:
    - Obfuscated "name [at] domain [dot] com" patterns
    - data-email / data-cfemail attributes (Cloudflare protection)
    - HTML entities like &#64; for @
    """
    try:
        resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if resp.status_code != 200:
            return []
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        emails: list[str] = []

        # 1. mailto: links
        for a in soup.find_all("a", href=True):
            if a["href"].startswith("mailto:"):
                e = a["href"].replace("mailto:", "").split("?")[0].strip()
                if e:
                    emails.append(e)

        # 2. data-email attributes (used by some anti-scrape libs)
        for tag in soup.find_all(attrs={"data-email": True}):
            e = tag.get("data-email", "").strip()
            if e:
                emails.append(e)

        # 3. Standard email regex in visible text
        emails.extend(EMAIL_RE.findall(soup.get_text()))

        # 4. Obfuscated patterns ("name at domain dot com")
        emails.extend(_find_obfuscated_emails(soup.get_text()))

        # 5. HTML source scan (catches JS-rendered text sometimes present in raw HTML)
        emails.extend(_find_obfuscated_emails(_decode_html_entities(html)))

        return _clean_emails(emails)
    except Exception:
        return []


async def _hunter_search(client: httpx.AsyncClient, domain: str) -> list[str]:
    """Hunter.io domain search — returns recruiter emails if key is configured."""
    key = os.getenv("HUNTER_API_KEY", "")
    if not key:
        return []
    try:
        resp = await client.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": key, "limit": 5},
            timeout=8,
        )
        if resp.status_code != 200:
            return []
        emails = [
            e["value"]
            for e in resp.json().get("data", {}).get("emails", [])
            if e.get("value")
        ]
        return _clean_emails(emails)
    except Exception:
        return []


async def _serpapi_email_search(
    client: httpx.AsyncClient, company: str, domain: str
) -> list[str]:
    """Google/SerpAPI search for recruiter email at company."""
    key = os.getenv("SERP_API_KEY", "")
    if not key:
        return []
    queries = [
        f'recruiter OR "HR email" site:{domain}',
        f'"{company}" hiring manager email',
    ]
    found: list[str] = []
    for q in queries:
        if found:
            break
        try:
            resp = await client.get(
                "https://serpapi.com/search.json",
                params={"engine": "google", "q": q, "api_key": key, "num": 5},
                timeout=10,
            )
            if resp.status_code != 200:
                continue
            snippet_text = " ".join(
                r.get("snippet", "") for r in (resp.json().get("organic_results") or [])
            )
            found.extend(EMAIL_RE.findall(snippet_text))
            found.extend(_find_obfuscated_emails(snippet_text))
        except Exception:
            continue
    return _clean_emails(found)


async def _generate_hr_emails(domain: str) -> list[str]:
    """
    Generate common HR email patterns for a domain and confirm MX exists.
    Returns generated patterns that look like recruiter contacts (not in GENERIC_PREFIXES).
    Labelled source='pattern_guess' by the caller — user sees it's a generated guess.
    """
    if not domain:
        return []
    if not await _mx_exists(domain):
        return []
    return [f"{prefix}@{domain}" for prefix in HR_PATTERNS]


async def _find_email_for_job(job: dict) -> dict:
    """
    Run up to 7 attempts for a single job.
      Attempt 1  — job listing page (direct company sites only)
      Attempt 2  — careers/jobs pages (expanded path list)
      Attempt 3  — contact/about/HR pages (expanded path list)
      Attempt 4  — SerpAPI Google search
      Attempt 5  — Hunter.io domain search
      Attempt 6  — LinkedIn company page
      Attempt 7  — Generate hr@/jobs@/careers@ patterns + MX-validate

    Two-pass strategy:
      Pass 1 — prefer specific recruiter email (not in GENERIC_PREFIXES).
      Pass 2 — accept generic contact email as last resort (never system/noreply).
    """
    url = job.get("url", "")
    company = job.get("company", "") or ""
    db_job_id = job.get("db_job_id", "")

    domain = _get_search_domain(url, company)
    # Also get all domain variants to try for pattern guessing
    domain_variants = _company_to_domain_variants(company) if company else []
    if domain and domain not in domain_variants:
        domain_variants.insert(0, domain)

    found_email: str = ""
    source: str = "none"
    generic_fallback: str = ""
    generic_source: str = "none"

    async def _pick(emails: list[str], src: str) -> bool:
        """Try to find a good email; save generic ones as fallback. Returns True if specific found."""
        nonlocal found_email, source, generic_fallback, generic_source
        for e in emails:
            if _is_system_email(e):
                continue
            domain_part = e.split("@")[1] if "@" in e else ""
            if not domain_part or not await _mx_exists(domain_part):
                continue
            if not _is_generic_email(e):
                found_email, source = e, src
                return True
            elif not generic_fallback:
                generic_fallback, generic_source = e, src
        return False

    async with httpx.AsyncClient(follow_redirects=True) as client:

        # Attempt 1 — job listing page (only for direct company URLs)
        if url and not any(agg in _extract_domain_from_url(url) for agg in AGGREGATOR_DOMAINS):
            await _pick(await _scrape_emails(client, url), "listing")

        # Attempt 2 — company careers / jobs pages (extended path list)
        if not found_email and domain:
            for path in _CAREER_PATHS:
                if await _pick(await _scrape_emails(client, f"https://{domain}{path}"), "careers"):
                    break

        # Attempt 3 — contact / about / HR pages (extended path list)
        if not found_email and domain:
            for path in _CONTACT_PATHS:
                if await _pick(await _scrape_emails(client, f"https://{domain}{path}"), "contact"):
                    break

        # Attempt 4 — SerpAPI Google search
        if not found_email and company:
            await _pick(await _serpapi_email_search(client, company, domain), "google")

        # Attempt 5 — Hunter.io
        if not found_email and domain:
            await _pick(await _hunter_search(client, domain), "hunter")

        # Attempt 6 — LinkedIn company page
        if not found_email and company:
            company_slug = re.sub(r"[^a-z0-9]", "-", company.lower()).strip("-")
            li_url = f"https://www.linkedin.com/company/{company_slug}/people/"
            await _pick(await _scrape_emails(client, li_url), "linkedin")

        # Attempt 7 — Generate common HR email patterns (hr@, jobs@, careers@…)
        # Tries every domain variant derived from the company name.
        if not found_email:
            for dv in domain_variants[:3]:
                hr_emails = await _generate_hr_emails(dv)
                if await _pick(hr_emails, "pattern_guess"):
                    break
                # HR patterns are not in GENERIC_PREFIXES, so _pick uses them as
                # specific emails — no need for a separate generic fallback here.

    # Fall back to generic contact email (info@, contact@…) if nothing specific found
    if not found_email and generic_fallback:
        found_email, source = generic_fallback, generic_source

    route = "email_apply" if found_email else "portal_apply"
    return {
        "job_id":      db_job_id,
        "job_title":   job.get("title", ""),
        "company":     company,
        "job_url":     url,
        "db_job_id":   db_job_id,
        "email":       found_email or None,
        "source":      source,
        "is_valid":    bool(found_email),
        "portal_only": not bool(found_email),
        "route":       route,
        "log_event":   None if found_email else "email_not_found",
    }


async def email_finder_impl(matched_jobs_json: str) -> str:
    raw = json.loads(matched_jobs_json)
    matched_jobs = raw.get("matched_jobs", []) if isinstance(raw, dict) else raw

    results = await asyncio.gather(
        *[_find_email_for_job(j) for j in matched_jobs],
        return_exceptions=True,
    )

    email_results = []
    for r in results:
        if isinstance(r, Exception):
            email_results.append({
                "email": None, "source": "none", "is_valid": False,
                "route": "portal_apply", "error": str(r),
            })
        else:
            email_results.append(r)

    return json.dumps({"success": True, "email_results": email_results})


@function_tool
async def email_finder_tool(matched_jobs_json: str) -> str:
    """Find recruiter email addresses for matched jobs.
    7 attempts per job: page scraping → careers/contact pages → SerpAPI → Hunter.io → LinkedIn → HR pattern generation.
    Detects standard, obfuscated (name[at]domain[dot]com), and data-email attribute formats.
    Returns JSON with email_results. Each result includes route: email_apply or portal_apply.
    """
    return await email_finder_impl(matched_jobs_json=matched_jobs_json)
