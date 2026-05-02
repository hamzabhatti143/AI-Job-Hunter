"""
Company name finder — three-stage pipeline:
  1. Scrape job page   → extract structured hints (JSON-LD, meta, OG, title, domain)
  2. LLM (Gemini Flash Lite) → infer company name from hints
  3. Google verify     → confirm the name is real before returning it

Call `find_company_name(job_title, job_url)` from anywhere.
"""
import os, re, json
import httpx
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False

_BAD_NAMES = {
    "", "n/a", "na", "unknown", "various", "multiple", "confidential",
    "anonymous", "undisclosed", "not specified", "not disclosed",
    "your organization", "your company", "your organisation",
    "organization", "organisation", "company", "employer",
    "hiring company", "hiring organization", "our client", "a client",
    "leading company", "top company", "mnc", "acca listed",
}

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"


# ── Stage 1: scrape job page for company hints ────────────────────────────────

async def _scrape_company_hints(client: httpx.AsyncClient, url: str) -> dict:
    """Fetch job page and extract every clue about the company name."""
    hints: dict = {}
    if not url:
        return hints
    try:
        r = await client.get(url, timeout=12, headers={"User-Agent": _UA})
        if r.status_code >= 400:
            return hints
        html = r.text

        if _BS4:
            soup = BeautifulSoup(html, "html.parser")

            # JSON-LD — most reliable
            for tag in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(tag.string or "")
                    if isinstance(data, list):
                        data = next((d for d in data if isinstance(d, dict)), {})
                    org = data.get("hiringOrganization") or {}
                    if isinstance(org, dict) and org.get("name"):
                        hints["jsonld"] = org["name"]
                    elif data.get("@type") == "Organization" and data.get("name"):
                        hints["jsonld"] = data["name"]
                    publisher = data.get("publisher") or {}
                    if isinstance(publisher, dict) and publisher.get("name") and "jsonld" not in hints:
                        hints["jsonld"] = publisher["name"]
                except Exception:
                    pass
                if "jsonld" in hints:
                    break

            # OpenGraph site name
            og = soup.find("meta", property="og:site_name")
            if og and og.get("content"):
                hints["og_site"] = og["content"]

            # application-name meta
            app = soup.find("meta", attrs={"name": "application-name"})
            if app and app.get("content"):
                hints["app_name"] = app["content"]

            # twitter:site
            tw = soup.find("meta", attrs={"name": "twitter:site"})
            if tw and tw.get("content"):
                hints["twitter_site"] = tw["content"].lstrip("@")

            # Page <title> — often "Job Title | Company Name" or "Company – Job"
            title_tag = soup.find("title")
            if title_tag:
                hints["page_title"] = title_tag.get_text(strip=True)

            # <h1> — sometimes "Company is hiring a Job Title"
            h1 = soup.find("h1")
            if h1:
                hints["h1"] = h1.get_text(strip=True)[:120]

        else:
            # Fallback without BS4 — regex-based
            m = re.search(r'"hiringOrganization"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', html)
            if m:
                hints["jsonld"] = m.group(1)
            m2 = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
            if m2:
                hints["page_title"] = m2.group(1).strip()

    except Exception:
        pass

    # Domain-based hint — always add as last resort
    try:
        hostname = urlparse(url).netloc.lower()
        hostname = re.sub(r"^(www\.|careers\.|jobs\.|apply\.|talent\.)", "", hostname)
        domain_word = hostname.split(".")[0]
        if domain_word and len(domain_word) >= 3:
            hints["domain_word"] = domain_word
    except Exception:
        pass

    return hints


# ── Stage 2: LLM infers company name from hints ────────────────────────────────

async def _llm_company_from_hints(job_title: str, url: str, hints: dict) -> str:
    """Gemini Flash Lite: infer company name from scraped hints. Max 20 tokens."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return ""

    hints_lines = "\n".join(f"  {k}: {v}" for k, v in hints.items() if v) or "  (no hints)"
    prompt = (
        f'Job title: "{job_title}"\n'
        f'Job URL: "{url}"\n'
        f'Page hints extracted:\n{hints_lines}\n\n'
        f'Based on the above, what is the hiring company name? '
        f'Reply with ONLY the company name — nothing else. '
        f'If you truly cannot determine it, reply: unknown'
    )
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent",
                params={"key": key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 20, "temperature": 0.0},
                },
            )
        if r.status_code == 200:
            raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            name = raw.strip().strip('"').strip("'")
            if name.lower() in ("unknown", "n/a", "") or len(name) < 2 or len(name) > 80:
                return ""
            return name
    except Exception:
        pass
    return ""


# ── Stage 3: Google verify ─────────────────────────────────────────────────────

async def _google_verify_company(client: httpx.AsyncClient, company_name: str) -> str:
    """
    Quick SerpAPI search to confirm the company name is real.
    Returns the (possibly corrected) company name, or the original if verification
    cannot be done (no API key, timeout, etc.).
    """
    key = os.getenv("SERPAPI_KEY", "")
    if not key or not company_name:
        return company_name  # can't verify — return as-is

    try:
        r = await client.get(
            "https://serpapi.com/search",
            params={
                "engine": "google",
                "q": f'"{company_name}" company',
                "num": "5",
                "api_key": key,
            },
            timeout=10,
        )
        if r.status_code != 200:
            return company_name

        results = r.json().get("organic_results", [])
        if not results:
            return company_name

        name_lower = company_name.lower()
        # Check if the company name appears in any of the top result titles/snippets
        for res in results[:5]:
            text = (res.get("title", "") + " " + res.get("snippet", "")).lower()
            if name_lower in text:
                return company_name  # confirmed

        # Not found in results — might be misspelled, return first knowledge panel if present
        kg = r.json().get("knowledge_graph", {})
        if kg.get("title"):
            return kg["title"]

    except Exception:
        pass

    return company_name  # assume correct on error


# ── Public API ────────────────────────────────────────────────────────────────

async def find_company_name(job_title: str, job_url: str) -> str:
    """
    Full 3-stage pipeline:
      1. Scrape job page for structured hints
      2. LLM infers company name from hints
      3. Google search verifies/confirms the name

    Returns the confirmed company name, or "" if all stages fail.
    """
    from job_agent.tools.job_scraper import _clean_company

    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": _UA},
        timeout=15,
    ) as client:

        # Stage 1 — scrape hints
        hints = await _scrape_company_hints(client, job_url)

        # Fast path: JSON-LD gave us a clean name → verify directly
        jsonld_name = _clean_company(hints.get("jsonld", ""))
        if jsonld_name and jsonld_name.lower() not in _BAD_NAMES and len(jsonld_name) >= 2:
            return await _google_verify_company(client, jsonld_name)

        # Stage 2 — LLM with hints
        llm_name = await _llm_company_from_hints(job_title, job_url, hints)
        if llm_name:
            cleaned = _clean_company(llm_name)
            if cleaned and cleaned.lower() not in _BAD_NAMES:
                # Stage 3 — Google verify
                return await _google_verify_company(client, cleaned)

    return ""
