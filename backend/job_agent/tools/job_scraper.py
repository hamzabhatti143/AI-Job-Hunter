"""STEP 3 — Search jobs from multiple sources using role, skills and location.

Location is ALWAYS from the user's UI input — never from the resume.
Universal geocoding via Nominatim (OpenStreetMap, free, no API key required).
"""
import json
import re
import asyncio
import os
import datetime
import xml.etree.ElementTree as ET
import httpx
from agents import function_tool

# ── Location system ──────────────────────────────────────────────────────────
#
# Strategy:
#   1. Detect remote/global keywords first (no geocoding needed)
#   2. Call Nominatim (free OpenStreetMap geocoding) to resolve ANY city/country/state
#   3. Build 3 search variants from the structured geocode result
#   4. Supplement filter_terms with known cities for country-level searches
#   5. Fall back to heuristics if geocoding fails/times out
# ──────────────────────────────────────────────────────────────────────────────

_REMOTE_TERMS = frozenset([
    "remote", "wfh", "work from home", "work-from-home", "anywhere",
    "worldwide", "global", "distributed", "fully remote", "no office",
])

# Remote location terms — jobs matching these always pass the location filter
_REMOTE_FILTER_TERMS = frozenset([
    "remote", "worldwide", "anywhere", "global", "wfh",
    "work from home", "distributed", "fully remote",
])

# Supplement filter terms for country-level searches (city names that might
# appear in job listings without the country name).
# Only needed for common countries — Nominatim handles the rest via country/code.
_COUNTRY_CITIES: dict[str, list[str]] = {
    "Pakistan":       ["karachi","lahore","islamabad","rawalpindi","faisalabad","multan","peshawar","quetta","sialkot","gujranwala"],
    "India":          ["mumbai","delhi","bangalore","hyderabad","chennai","pune","kolkata","ahmedabad","jaipur","surat"],
    "United States":  ["new york","san francisco","los angeles","chicago","seattle","austin","boston","denver","miami","dallas"],
    "United Kingdom": ["london","manchester","birmingham","glasgow","edinburgh","bristol","leeds","sheffield"],
    "Canada":         ["toronto","vancouver","montreal","calgary","ottawa","edmonton"],
    "Australia":      ["sydney","melbourne","brisbane","perth","adelaide","canberra"],
    "Germany":        ["berlin","munich","hamburg","frankfurt","cologne","stuttgart","dusseldorf"],
    "France":         ["paris","lyon","marseille","toulouse","bordeaux","lille"],
    "Netherlands":    ["amsterdam","rotterdam","the hague","utrecht","eindhoven"],
    "Saudi Arabia":   ["riyadh","jeddah","dammam","mecca","medina","khobar"],
    "United Arab Emirates": ["dubai","abu dhabi","sharjah","ajman"],
    "Nigeria":        ["lagos","abuja","kano","ibadan","port harcourt","benin city"],
    "Kenya":          ["nairobi","mombasa","kisumu","nakuru"],
    "Ghana":          ["accra","kumasi","tamale"],
    "South Africa":   ["johannesburg","cape town","durban","pretoria"],
    "Egypt":          ["cairo","alexandria","giza","sharm el sheikh"],
    "Turkey":         ["istanbul","ankara","izmir","bursa","antalya"],
    "Bangladesh":     ["dhaka","chittagong","rajshahi","khulna"],
    "Philippines":    ["manila","cebu","davao","quezon city"],
    "Indonesia":      ["jakarta","surabaya","bandung","medan","bekasi"],
    "Malaysia":       ["kuala lumpur","penang","johor bahru","kota kinabalu"],
    "Brazil":         ["sao paulo","rio de janeiro","brasilia","fortaleza","belo horizonte"],
    "Mexico":         ["mexico city","guadalajara","monterrey","puebla","tijuana"],
    "Argentina":      ["buenos aires","cordoba","rosario","mendoza"],
    "Poland":         ["warsaw","krakow","wroclaw","gdansk","poznan"],
    "Sweden":         ["stockholm","gothenburg","malmo","uppsala"],
    "Norway":         ["oslo","bergen","trondheim"],
    "Denmark":        ["copenhagen","aarhus","odense"],
    "Switzerland":    ["zurich","geneva","bern","basel","lausanne"],
    "Spain":          ["madrid","barcelona","seville","valencia","bilbao"],
    "Italy":          ["rome","milan","naples","turin","florence"],
    "Japan":          ["tokyo","osaka","kyoto","yokohama","nagoya"],
    "South Korea":    ["seoul","busan","incheon","daegu"],
    "China":          ["beijing","shanghai","shenzhen","guangzhou","chengdu"],
    "Singapore":      ["singapore"],
    "Qatar":          ["doha"],
    "Kuwait":         ["kuwait city"],
    "Bahrain":        ["manama"],
    "Oman":           ["muscat","salalah"],
}

# Multi-country regions
_REGION_MAP: dict[str, dict] = {
    "gulf":        {"countries": ["UAE","Saudi Arabia","Qatar","Kuwait","Bahrain","Oman"],
                    "cities":    ["dubai","abu dhabi","riyadh","jeddah","doha","kuwait city","manama","muscat"]},
    "middle east": {"countries": ["UAE","Saudi Arabia","Qatar","Kuwait","Bahrain","Oman","Jordan","Lebanon","Egypt","Turkey"],
                    "cities":    ["dubai","riyadh","doha","cairo","istanbul","amman","beirut","muscat"]},
    "europe":      {"countries": ["UK","Germany","France","Netherlands","Spain","Sweden","Norway","Denmark","Switzerland","Austria","Poland","Italy","Portugal","Belgium","Ireland"],
                    "cities":    ["london","berlin","paris","amsterdam","madrid","stockholm","oslo","copenhagen","zurich","vienna","warsaw","rome","lisbon","brussels","dublin"]},
    "south asia":  {"countries": ["Pakistan","India","Bangladesh","Sri Lanka","Nepal"],
                    "cities":    ["karachi","lahore","islamabad","mumbai","delhi","bangalore","dhaka","colombo","kathmandu"]},
    "africa":      {"countries": ["Nigeria","Kenya","Ghana","South Africa","Egypt","Ethiopia","Tanzania"],
                    "cities":    ["lagos","nairobi","accra","johannesburg","cairo","addis ababa","dar es salaam"]},
    "southeast asia": {"countries": ["Philippines","Indonesia","Malaysia","Singapore","Thailand","Vietnam"],
                       "cities":    ["manila","jakarta","kuala lumpur","singapore","bangkok","ho chi minh city","hanoi"]},
    "latam":       {"countries": ["Brazil","Mexico","Argentina","Colombia","Chile"],
                    "cities":    ["sao paulo","mexico city","buenos aires","bogota","santiago"]},
}


def _is_remote_input(location: str) -> bool:
    return location.strip().lower() in _REMOTE_TERMS


def _check_region(location: str) -> dict | None:
    """Return region info if the input matches a known multi-country region."""
    loc_lower = location.strip().lower()
    for key, data in _REGION_MAP.items():
        if key in loc_lower or loc_lower in key:
            countries = data["countries"]
            cities    = data["cities"]
            all_terms = countries + cities
            return {
                "is_remote": False, "is_region": True,
                "search_terms": list(dict.fromkeys(all_terms)),
                "filter_terms": [t.lower() for t in all_terms],
                "city": None, "country": None, "country_code": None,
                "region": key.title(), "fallback_country": None,
                "geocoded": False,
            }
    return None


async def _geocode_nominatim(location: str, client: httpx.AsyncClient) -> dict | None:
    """
    Universal geocoding via Nominatim (OpenStreetMap).
    Works for any city, state, country, or region worldwide. Free, no API key.
    Returns structured address data or None if lookup fails.
    Always requests English names via Accept-Language header.
    """
    try:
        resp = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location, "format": "json", "limit": 1, "addressdetails": 1},
            headers={"User-Agent": "AIJobHunter/1.0", "Accept-Language": "en"},
            timeout=4,
        )
        if resp.status_code != 200:
            return None
        results = resp.json()
        if not results:
            return None

        item = resp.json()[0]
        addr = item.get("address", {})
        return {
            "city":         (addr.get("city") or addr.get("town") or
                             addr.get("village") or addr.get("municipality") or
                             addr.get("county") or ""),
            "state":        addr.get("state") or addr.get("region") or "",
            "country":      addr.get("country") or "",
            "country_code": (addr.get("country_code") or "").upper(),
            "place_type":   item.get("type", ""),
            "display_name": item.get("display_name", ""),
        }
    except Exception:
        return None


def _build_loc_info(location: str, geo: dict | None) -> dict:
    """
    Build unified loc_info from Nominatim geocode result (or fallback heuristics).

    Produces:
      search_terms  — 3 variants to inject into job queries (specific → broad)
      filter_terms  — lowercase terms; job location must contain at least one
      fallback_country — for retry logic: city → country, country → None
    """
    loc = location.strip()

    if geo:
        city    = geo.get("city", "")
        state   = geo.get("state", "")
        country = geo.get("country", "")
        code    = geo.get("country_code", "")   # e.g. "PK", "DE", "NG"

        # ── Build 3 search variants ──────────────────────────────────
        # Variant A: exact text as typed
        variant_a = loc
        # Variant B: city/state + country (inferred)
        if city and country:
            variant_b = f"{city} {country}"
        elif state and country:
            variant_b = f"{state} {country}"
        else:
            variant_b = country or loc
        # Variant C: ISO code or state abbreviation
        variant_c = code if code else variant_b

        terms = list(dict.fromkeys([variant_a, variant_b, variant_c]))

        # ── Build filter terms (STRICT per search level) ─────────────
        # City-level:    ONLY city + state.  Country/code are NOT added —
        #                otherwise "Pakistan" jobs pass a "Karachi" filter.
        # Country-level: country + code + major cities.
        filter_terms: list[str] = []
        is_country_level = (not city) or (city.lower() == country.lower())

        if not is_country_level:
            # City-level: strict to city and state only
            for t in [city, state, loc]:
                if t:
                    ft = t.lower()
                    if ft not in filter_terms:
                        filter_terms.append(ft)
        else:
            # Country-level: include country, code, and major cities
            for t in [country, code, loc]:
                if t:
                    ft = t.lower()
                    if ft not in filter_terms:
                        filter_terms.append(ft)
            country_cities = (
                _COUNTRY_CITIES.get(country, []) or
                _COUNTRY_CITIES.get(loc.title(), []) or
                _COUNTRY_CITIES.get(loc, [])
            )
            if country_cities:
                filter_terms.extend(country_cities)
                for c in country_cities[:3]:
                    terms.append(c.title())
        fallback_country = country if (city and city.lower() != country.lower()) else None

        return {
            "is_remote": False, "is_region": False, "geocoded": True,
            "search_terms": list(dict.fromkeys(terms)),
            "filter_terms": list(dict.fromkeys(filter_terms)),
            "city": city, "state": state, "country": country, "country_code": code,
            "fallback_country": fallback_country,
        }

    # ── Fallback: no geocoding result — use raw input ────────────────
    loc_lower = loc.lower()
    # Only add city list if the raw input is a KNOWN COUNTRY name.
    # If it's a city name we can't identify, only filter by that string.
    known_cities = _COUNTRY_CITIES.get(loc.title(), []) or _COUNTRY_CITIES.get(loc, [])
    if known_cities:
        # It's a known country — country-level filter
        filter_terms = [loc_lower] + known_cities
    else:
        # Unknown or city name — strict: only the raw input
        filter_terms = [loc_lower]

    return {
        "is_remote": False, "is_region": False, "geocoded": False,
        "search_terms": [loc],
        "filter_terms": list(dict.fromkeys(filter_terms)),
        "city": "", "state": "", "country": loc, "country_code": "",
        "fallback_country": None,
    }


def _expand_location(location: str) -> dict:
    """
    Sync fallback — used by pipeline when async geocoding isn't available.
    For remote/global inputs only; real geocoding runs inside job_scraper_impl.
    """
    if _is_remote_input(location):
        return {
            "is_remote": True, "is_region": False, "geocoded": False,
            "search_terms": ["Remote", "Work from home", "WFH", "Anywhere"],
            "filter_terms": [], "city": None, "country": None, "country_code": None,
            "fallback_country": None,
        }
    region = _check_region(location)
    if region:
        return region
    # No geocoding — return minimal info, geocoding will enrich at scrape time
    loc_lower = location.strip().lower()
    return {
        "is_remote": False, "is_region": False, "geocoded": False,
        "search_terms": [location.strip()],
        "filter_terms": [loc_lower],
        "city": "", "country": location.strip(), "country_code": "",
        "fallback_country": None,
    }




# ── Helper ────────────────────────────────────────────────────────────────────

def _to_tag(s: str) -> str:
    return s.lower().strip().replace(" ", "-").replace(".", "-").replace("/", "-")


def _build_search_terms(role: str, skills: list[str]) -> list[str]:
    terms: list[str] = []
    if role:
        terms.append(role.strip())
    stopwords = {"and", "the", "for", "with", "from", "that", "this", "are", "was"}
    if role:
        for word in role.split():
            w = word.strip().lower()
            if len(w) > 3 and w not in stopwords and w not in [t.lower() for t in terms]:
                terms.append(w)
    for skill in skills[:4]:
        sk = skill.strip()
        if sk and sk.lower() not in [t.lower() for t in terms]:
            terms.append(sk)
    return terms


# ── Sources ───────────────────────────────────────────────────────────────────

async def _fetch_remoteok(client: httpx.AsyncClient, terms: list[str]) -> list[dict]:
    """RemoteOK — remote jobs by tag."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    jobs: list[dict] = []
    seen: set[str] = set()
    for term in terms:
        if len(jobs) >= 20:
            break
        tag = _to_tag(term)
        try:
            url = f"https://remoteok.com/api?tag={tag}"
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
                    "title": item.get("position", ""), "company": item.get("company", ""),
                    "location": item.get("location") or "Remote", "url": job_url,
                    "description": (item.get("description") or "")[:800],
                    "tags": item.get("tags") or [], "source": "remoteok",
                })
        except Exception:
            continue
    return jobs


async def _fetch_remotive(client: httpx.AsyncClient, role: str, skills: list[str]) -> list[dict]:
    """Remotive — remote jobs by search term."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    jobs: list[dict] = []
    seen: set[str] = set()
    for term in ([role] + [s for s in skills[:3] if s.lower() not in role.lower()]):
        if not term:
            continue
        try:
            resp = await client.get(
                "https://remotive.com/api/remote-jobs",
                params={"search": term, "limit": 15},
                headers=headers, timeout=15,
            )
            if resp.status_code != 200:
                continue
            for item in (resp.json().get("jobs") or []):
                job_url = item.get("url", "")
                if not job_url or job_url in seen:
                    continue
                seen.add(job_url)
                jobs.append({
                    "title": item.get("title", ""), "company": item.get("company_name", ""),
                    "location": item.get("candidate_required_location") or "Remote",
                    "url": job_url, "description": (item.get("description") or "")[:800],
                    "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                    "source": "remotive",
                })
        except Exception:
            continue
    return jobs


async def _fetch_weworkremotely(client: httpx.AsyncClient, role: str, skills: list[str]) -> list[dict]:
    """We Work Remotely — free RSS feed."""
    headers = {"User-Agent": "Mozilla/5.0"}
    jobs: list[dict] = []
    seen: set[str] = set()
    terms = [role] + [s for s in skills[:2] if s.lower() not in role.lower()]
    for term in terms:
        if len(jobs) >= 20 or not term:
            break
        try:
            resp = await client.get(
                "https://weworkremotely.com/remote-jobs.rss",
                params={"term": term}, headers=headers, timeout=15,
            )
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            ns = {"wwr": "https://weworkremotely.com"}
            for item in root.findall(".//item"):
                title_el = item.find("title")
                link_el  = item.find("link")
                desc_el  = item.find("description")
                region_el = item.find("wwr:region", ns)

                if title_el is None or link_el is None:
                    continue
                raw_title = (title_el.text or "").strip()
                url = (link_el.text or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)

                # Title format: "Company Name: Job Title"
                if ": " in raw_title:
                    company, title = raw_title.split(": ", 1)
                else:
                    company, title = "", raw_title

                region = (region_el.text if region_el is not None else "") or "Remote"
                jobs.append({
                    "title": title, "company": company, "location": region,
                    "url": url, "description": (desc_el.text or "")[:800],
                    "tags": [], "source": "weworkremotely",
                })
        except Exception:
            continue
    return jobs


async def _fetch_arbeitnow(client: httpx.AsyncClient, role: str, location: str) -> list[dict]:
    """Arbeitnow — international jobs with location support."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    jobs: list[dict] = []
    seen: set[str] = set()
    # Only search with explicit location — no empty fallback (avoids all-jobs dump)
    params_list: list[dict] = [{"search": role, "location": location}] if location else [{"search": role}]
    for params in params_list:
        if not params.get("search"):
            continue
        try:
            resp = await client.get(
                "https://www.arbeitnow.com/api/job-board-api",
                params=params, headers=headers, timeout=15,
            )
            if resp.status_code != 200:
                continue
            for item in (resp.json().get("data") or []):
                job_url = item.get("url", "")
                if not job_url or job_url in seen:
                    continue
                seen.add(job_url)
                # Use "" not "Remote" — let the pipeline filter decide
                jobs.append({
                    "title": item.get("title", ""), "company": item.get("company_name", ""),
                    "location": item.get("location") or "",
                    "url": job_url, "description": (item.get("description") or "")[:800],
                    "tags": item.get("tags") or [], "source": "arbeitnow",
                })
        except Exception:
            continue
    return jobs


async def _fetch_findwork(client: httpx.AsyncClient, role: str, location: str) -> list[dict]:
    """Findwork.dev — supports role + location."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    jobs: list[dict] = []
    seen: set[str] = set()
    try:
        params: dict = {"search": role, "page": 1}
        if location:
            params["location"] = location
        resp = await client.get("https://findwork.dev/api/jobs/", params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            for item in (resp.json().get("results") or []):
                job_url = item.get("url", "")
                if not job_url or job_url in seen:
                    continue
                seen.add(job_url)
                jobs.append({
                    "title": item.get("role", ""), "company": item.get("company_name", ""),
                    "location": item.get("location") or "",
                    "url": job_url, "description": (item.get("text") or "")[:800],
                    "tags": item.get("keywords") or [], "source": "findwork",
                })
    except Exception:
        pass
    return jobs


async def _fetch_jobicy(client: httpx.AsyncClient, role: str, location: str) -> list[dict]:
    """Jobicy — global jobs with geo filter."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    jobs: list[dict] = []
    seen: set[str] = set()
    geo = location.strip().split(",")[0].strip().lower().replace(" ", "-") if location else ""
    # Only add geo param when meaningful; never fall back to all-jobs dump
    params: dict = {"count": 50, "tag": _to_tag(role)}
    if geo and geo not in ("remote", "anywhere", "worldwide"):
        params["geo"] = geo
    try:
        resp = await client.get("https://jobicy.com/api/v0/jobs", params=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            return jobs
        for item in (resp.json().get("jobs") or []):
            job_url = item.get("jobExcerptLink") or item.get("jobGeo", "")
            if not job_url or job_url in seen:
                continue
            seen.add(job_url)
            jobs.append({
                "title": item.get("jobTitle", ""), "company": item.get("companyName", ""),
                "location": item.get("jobGeo") or item.get("jobRegion") or "",
                "url": job_url, "description": (item.get("jobDescription") or "")[:800],
                "tags": item.get("jobIndustry") or [], "source": "jobicy",
            })
    except Exception:
        pass
    return jobs


async def _fetch_themuse(client: httpx.AsyncClient, role: str, location: str) -> list[dict]:
    """The Muse — global jobs with location support."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    jobs: list[dict] = []
    seen: set[str] = set()
    params: dict = {"page": 0, "descending": "true"}
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
        resp = await client.get("https://www.themuse.com/api/public/jobs", params=params, headers=headers, timeout=15)
        if resp.status_code == 200:
            for item in (resp.json().get("results") or []):
                job_url = item.get("refs", {}).get("landing_page", "")
                if not job_url or job_url in seen:
                    continue
                seen.add(job_url)
                locs = item.get("locations") or []
                loc_str = ", ".join(l.get("name", "") for l in locs if l.get("name")) or ""
                jobs.append({
                    "title": item.get("name", ""), "company": (item.get("company") or {}).get("name", ""),
                    "location": loc_str, "url": job_url,
                    "description": (item.get("contents") or "")[:800],
                    "tags": [item.get("category", {}).get("name", "")] if item.get("category") else [],
                    "source": "themuse",
                })
    except Exception:
        pass
    return jobs


async def _fetch_serpapi(
    client: httpx.AsyncClient, role: str, loc_info: dict, api_key: str
) -> list[dict]:
    """
    Google Jobs via SerpAPI — aggregates LinkedIn, Indeed, Glassdoor, Rozee.pk and more.
    Accepts pre-geocoded loc_info so location is never re-computed.

    Per-source format (Google Jobs engine):
      q        = "{role} jobs in {variant} {year}"
      location = "{city}, {country}" or "{country}" or "Worldwide"
      engine   = google_jobs
    """
    if not api_key:
        return []
    jobs: list[dict] = []
    seen: set[str] = set()
    year = datetime.date.today().year

    is_remote = loc_info.get("is_remote", False)

    # Build Google Jobs location param — city+country is most accurate
    city    = loc_info.get("city", "")
    country = loc_info.get("country", "")
    if is_remote:
        serp_location = "Worldwide"
    elif city and country:
        serp_location = f"{city}, {country}"
    elif country:
        serp_location = country
    else:
        serp_location = loc_info["search_terms"][0] if loc_info.get("search_terms") else ""

    # Build queries using all 3 location variants (A=exact, B=city+country, C=ISO)
    queries: list[str] = []
    if is_remote:
        queries.append(f"{role} remote jobs {year}")
    else:
        for variant in loc_info.get("search_terms", [])[:3]:
            q = f"{role} jobs in {variant} {year}"
            if q not in queries:
                queries.append(q)

    for query in queries:
        if len(jobs) >= 50:
            break
        try:
            resp = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_jobs",
                    "q": query,
                    "location": serp_location,
                    "api_key": api_key,
                    "num": 20,
                },
                timeout=20,
            )
            if resp.status_code != 200:
                continue
            for item in (resp.json().get("jobs_results") or []):
                apply_options = item.get("apply_options") or []
                job_url = apply_options[0].get("link", "") if apply_options else ""
                if not job_url:
                    job_url = (item.get("related_links") or [{}])[0].get("link", "")

                dedup_key = f"{item.get('title','')}|{item.get('company_name','')}".lower()
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                if job_url:
                    seen.add(job_url)

                desc_parts = []
                for h in (item.get("job_highlights") or []):
                    desc_parts.extend(h.get("items", []))

                jobs.append({
                    "title":       item.get("title", ""),
                    "company":     item.get("company_name", ""),
                    "location":    item.get("location") or "",  # empty → rejected by pipeline filter
                    "url":         job_url,
                    "description": " ".join(desc_parts)[:800],
                    "tags":        [],
                    "source":      "serpapi_google_jobs",
                })
        except Exception:
            continue
    return jobs


async def _fetch_adzuna(
    client: httpx.AsyncClient, role: str, loc_info: dict,
    app_id: str, app_key: str,
) -> list[dict]:
    """
    Adzuna — real job board aggregator.
    Accepts pre-geocoded loc_info. Uses ISO2 country code directly.

    Per-source format:
      what  = role
      where = city or country name
      Endpoint country = ISO2 mapped to Adzuna codes
    """
    if not app_id or not app_key:
        return []

    # Use geocoded ISO2 directly — no re-computing
    iso = (loc_info.get("country_code") or "").lower()
    ADZUNA_COUNTRIES = {
        "us": "us", "gb": "gb", "au": "au", "ca": "ca",
        "de": "de", "fr": "fr", "in": "in", "it": "it",
        "nz": "nz", "pl": "pl", "sg": "sg", "za": "za",
    }
    country_code = ADZUNA_COUNTRIES.get(iso, "gb")

    jobs: list[dict] = []
    seen: set[str] = set()
    is_remote = loc_info.get("is_remote", False)
    # Use city if available, else country name
    city    = loc_info.get("city", "")
    country = loc_info.get("country", "")
    search_where = city or country if not is_remote else ""

    try:
        params: dict = {
            "app_id": app_id, "app_key": app_key,
            "results_per_page": 20, "what": role,
            "content-type": "application/json",
        }
        if search_where:
            params["where"] = search_where

        resp = await client.get(
            f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1",
            params=params, timeout=15,
        )
        if resp.status_code == 200:
            for item in (resp.json().get("results") or []):
                job_url = item.get("redirect_url", "")
                if not job_url or job_url in seen:
                    continue
                seen.add(job_url)
                loc_label = (item.get("location") or {}).get("display_name") or country or ""
                jobs.append({
                    "title":       item.get("title", ""),
                    "company":     (item.get("company") or {}).get("display_name", ""),
                    "location":    loc_label,
                    "url":         job_url,
                    "description": (item.get("description") or "")[:800],
                    "tags":        item.get("category", {}).get("label", "").split(",") if item.get("category") else [],
                    "source":      "adzuna",
                })
    except Exception:
        pass
    return jobs


# ── New onsite-focused sources ────────────────────────────────────────────────

_BROWSER_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _extract_jsonld_jobs(html: str, source: str, base_url: str = "") -> list[dict]:
    """
    Extract Schema.org JobPosting objects from JSON-LD blocks in an HTML page.
    Many modern job boards embed structured data for search engines — we reuse it.
    """
    import re as _re
    jobs: list[dict] = []
    pattern = _re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        _re.DOTALL | _re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1).strip())
        except Exception:
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            # Support both single @type and @graph arrays
            type_val = item.get("@type", "")
            graph    = item.get("@graph", [])
            targets: list[dict] = []
            if type_val == "JobPosting":
                targets = [item]
            elif graph:
                targets = [g for g in graph if isinstance(g, dict) and g.get("@type") == "JobPosting"]

            for t in targets:
                # Location
                raw_loc = t.get("jobLocation") or {}
                if isinstance(raw_loc, list):
                    raw_loc = raw_loc[0] if raw_loc else {}
                addr     = raw_loc.get("address") or {} if isinstance(raw_loc, dict) else {}
                if isinstance(addr, str):
                    loc_str = addr
                else:
                    loc_str = ", ".join(filter(None, [
                        addr.get("addressLocality", ""),
                        addr.get("addressRegion", ""),
                        addr.get("addressCountry", ""),
                    ]))

                # Company
                org     = t.get("hiringOrganization") or {}
                company = org.get("name", "") if isinstance(org, dict) else str(org)

                url = t.get("url") or t.get("identifier") or base_url
                if not isinstance(url, str):
                    url = base_url

                desc_raw = t.get("description") or ""
                # Strip HTML tags from description
                import re as _r2
                desc = _r2.sub(r'<[^>]+>', ' ', desc_raw).strip()[:800]

                jobs.append({
                    "title":       t.get("title") or t.get("name", ""),
                    "company":     company,
                    "location":    loc_str,
                    "url":         url,
                    "description": desc,
                    "date":        t.get("datePosted", ""),
                    "tags":        [],
                    "source":      source,
                })
    return jobs


async def _fetch_brightspyre(
    client: httpx.AsyncClient, role: str, location: str
) -> list[dict]:
    """Brightspyre.com — Pakistan tech-focused job board. Microdata HTML extraction."""
    jobs: list[dict] = []
    seen: set[str]   = set()

    role_q = role.replace(" ", "+")
    search_url = f"https://brightspyre.com/jobs?q={role_q}"
    if location and location.lower() not in ("remote", "anywhere", "worldwide", "pakistan", ""):
        search_url += f"&location={location.replace(' ', '+')}"

    try:
        resp = await client.get(search_url, headers=_BROWSER_HEADERS, timeout=12)
        if resp.status_code != 200:
            return jobs
        html = resp.text

        # Brightspyre uses microdata — extract title+link from <a class="title-job">
        for m in re.finditer(
            r'<a[^>]+class="[^"]*title-job[^"]*"[^>]+href="(/jobs/[^"]+)"[^>]+title="([^"]+)"',
            html, re.IGNORECASE,
        ):
            href  = m.group(1).strip()
            title = m.group(2).replace(" - Job description", "").strip()
            url   = f"https://brightspyre.com{href}"
            if url in seen or not title:
                continue
            seen.add(url)

            # Try to find location near this job entry (look ahead in HTML)
            pos   = m.end()
            chunk = html[pos:pos + 600]
            loc_m = re.search(r'property="addressLocality"[^>]*>([^<]+)', chunk, re.IGNORECASE)
            loc_str = loc_m.group(1).strip() if loc_m else (location or "Pakistan")

            # Try company name
            comp_m = re.search(r'property="name"[^>]*>([^<]+)', chunk, re.IGNORECASE)
            company = comp_m.group(1).strip() if comp_m else ""

            jobs.append({
                "title":       title,
                "company":     company,
                "location":    loc_str,
                "url":         url,
                "description": "",
                "tags":        [],
                "source":      "smartrecruiters",
            })
    except Exception:
        pass

    return jobs[:20]


async def _fetch_smartrecruiters(
    client: httpx.AsyncClient, role: str, location: str
) -> list[dict]:
    """SmartRecruiters — delegates to Brightspyre for Pakistan/Gulf tech jobs."""
    return await _fetch_brightspyre(client, role, location)


async def _fetch_bayt(
    client: httpx.AsyncClient, role: str, location: str
) -> list[dict]:
    """Bayt.com — major MENA/Pakistan job board. Uses RSS feed (bypasses 403 bot blocking)."""
    jobs: list[dict] = []
    seen: set[str]   = set()

    role_q    = role.replace(" ", "+")
    loc_lower = location.lower() if location else ""

    # Bayt RSS feed — more bot-friendly than their HTML pages
    if "pakistan" in loc_lower or loc_lower in ("pk", "pakistan"):
        rss_urls = [
            f"https://www.bayt.com/en/pakistan/jobs/rss/?q={role_q}",
            f"https://www.bayt.com/en/rss/jobs/?q={role_q}&l=Pakistan",
        ]
    else:
        loc_q = location.replace(" ", "+") if location else ""
        rss_urls = [
            f"https://www.bayt.com/en/rss/jobs/?q={role_q}&l={loc_q}" if loc_q else f"https://www.bayt.com/en/rss/jobs/?q={role_q}",
        ]

    for rss_url in rss_urls:
        try:
            resp = await client.get(rss_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if resp.status_code == 200 and ("<rss" in resp.text or "<feed" in resp.text):
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item"):
                    title_el = item.find("title")
                    link_el  = item.find("link")
                    desc_el  = item.find("description")
                    if title_el is None or link_el is None:
                        continue
                    job_url = (link_el.text or "").strip()
                    title   = (title_el.text or "").strip()
                    if not job_url or job_url in seen:
                        continue
                    seen.add(job_url)
                    desc_raw = (desc_el.text or "") if desc_el is not None else ""
                    desc     = re.sub(r'<[^>]+>', ' ', desc_raw).strip()[:800]
                    # Bayt RSS title format: "Job Title - Company - Location"
                    parts = [p.strip() for p in title.split(" - ")]
                    job_title = parts[0] if parts else title
                    company   = parts[1] if len(parts) > 1 else ""
                    loc_str   = parts[2] if len(parts) > 2 else (location or "")
                    jobs.append({
                        "title": job_title, "company": company, "location": loc_str,
                        "url": job_url, "description": desc, "tags": [], "source": "bayt",
                    })
                if jobs:
                    break
        except Exception:
            continue

    # Fallback: try with Googlebot UA which often bypasses bot detection
    if not jobs:
        googlebot_headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Accept": "text/html,application/xhtml+xml",
        }
        role_slug = role.lower().replace(" ", "-")
        html_urls = (
            [f"https://www.bayt.com/en/pakistan/jobs/{role_slug}-jobs/"]
            if "pakistan" in loc_lower or loc_lower in ("pk",)
            else [f"https://www.bayt.com/en/international/jobs/?q={role_q}"]
        )
        for url in html_urls:
            try:
                resp = await client.get(url, headers=googlebot_headers, timeout=15)
                if resp.status_code != 200:
                    continue
                html = resp.text
                ld_jobs = _extract_jsonld_jobs(html, "bayt", url)
                if ld_jobs:
                    jobs.extend(ld_jobs)
                    break
                # HTML job card extraction
                for m in re.finditer(
                    r'data-job-id="(\d+)"[^>]*>.*?<a[^>]+href="(/en/[^"]+/jobs/[^"]+)"[^>]*>(.*?)</a>',
                    html, re.DOTALL | re.IGNORECASE,
                ):
                    href  = m.group(2).strip()
                    title = re.sub(r'<[^>]+>', '', m.group(3)).strip()
                    full_url = f"https://www.bayt.com{href}"
                    if title and full_url not in seen:
                        seen.add(full_url)
                        jobs.append({
                            "title": title, "company": "", "location": location or "",
                            "url": full_url, "description": "", "tags": [], "source": "bayt",
                        })
                if jobs:
                    break
            except Exception:
                continue

    return jobs[:20]


def _extract_js_object(html: str, var_name: str) -> dict | None:
    """
    Extract a JS variable assignment like `var NAME = {...};` from HTML using
    brace-balancing — safe for deeply nested JSON that regex can't handle.
    """
    m = re.search(rf'var\s+{re.escape(var_name)}\s*=\s*(\{{)', html)
    if not m:
        return None
    start = m.start(1)
    depth = 0
    for i, ch in enumerate(html[start:], start):
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start:i + 1])
                except Exception:
                    return None
    return None


async def _fetch_rozee(
    client: httpx.AsyncClient, role: str, location: str
) -> list[dict]:
    """Rozee.pk — Pakistan's largest job board. Extracts embedded `var apResp` JS data."""
    jobs: list[dict] = []
    seen: set[str]   = set()

    role_enc = role.replace(" ", "+")
    urls_to_try = [f"https://www.rozee.pk/job/jsearch/q/{role_enc}"]
    if location and location.lower() not in ("remote", "anywhere", "worldwide", "pakistan"):
        loc_enc = location.replace(" ", "%20")
        urls_to_try.append(f"https://www.rozee.pk/job/jsearch/q/{role_enc}/loc/{loc_enc}")

    for url in urls_to_try:
        try:
            resp = await client.get(url, headers=_BROWSER_HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            html = resp.text

            # Rozee embeds all jobs in: var apResp = { "response": { "jobs": { "basic": [...] } } }
            data = _extract_js_object(html, "apResp")
            if not data:
                continue
            jobs_data = data.get("response", {}).get("jobs", {})
            all_items = jobs_data.get("basic", []) + jobs_data.get("sponsored", [])

            for item in all_items:
                permalink = item.get("rozeePermaLink") or item.get("permaLink", "")
                job_url = f"https://www.rozee.pk/job/jsearch/apply-for-{permalink}" if permalink else ""
                if not job_url or job_url in seen:
                    continue
                seen.add(job_url)
                city    = item.get("city", "")
                country = item.get("country", "Pakistan")
                loc_str = f"{city}, {country}" if city else country
                raw_skills = item.get("skills", [])
                tags = raw_skills if isinstance(raw_skills, list) else []
                jobs.append({
                    "title":       item.get("title", ""),
                    "company":     item.get("company_name", ""),
                    "location":    loc_str,
                    "url":         job_url,
                    "description": (item.get("description_raw") or "")[:800],
                    "tags":        tags,
                    "source":      "rozee",
                })
            if jobs:
                break
        except Exception:
            continue

    return jobs[:20]


async def _fetch_acca_global(
    client: httpx.AsyncClient, role: str, location: str
) -> list[dict]:
    """ACCA Global jobs — finance/accounting board. HTML + JSON-LD extraction."""
    jobs: list[dict] = []
    seen: set[str]   = set()

    role_q = role.replace(" ", "+")
    loc_q  = location.replace(" ", "+") if location else ""

    # Their search page (more reliable than the RSS endpoint)
    search_urls = [
        f"https://jobs.accaglobal.com/jobs/results/?keywords={role_q}&locationname={loc_q}",
        f"https://jobs.accaglobal.com/jobs/results/?keywords={role_q}",
    ]

    for search_url in search_urls:
        try:
            resp = await client.get(search_url, headers=_BROWSER_HEADERS, timeout=15)
            if resp.status_code != 200:
                continue
            html = resp.text

            # JSON-LD first
            ld_jobs = _extract_jsonld_jobs(html, "acca_global", search_url)
            for j in ld_jobs:
                if j["url"] not in seen:
                    seen.add(j["url"])
                    jobs.append(j)

            # HTML fallback — ACCA uses standard job listing markup
            if not ld_jobs:
                for m in re.finditer(
                    r'<a[^>]+href="(https?://jobs\.accaglobal\.com/jobs/\d+[^"]*)"[^>]*>\s*<h[23][^>]*>\s*([^<]{5,150})\s*</h[23]>',
                    html, re.IGNORECASE | re.DOTALL,
                ):
                    job_url = m.group(1).strip()
                    title   = re.sub(r'\s+', ' ', m.group(2)).strip()
                    if job_url not in seen and title:
                        seen.add(job_url)
                        jobs.append({
                            "title": title, "company": "ACCA Listed",
                            "location": location or "", "url": job_url,
                            "description": "", "tags": ["finance", "accounting"], "source": "acca_global",
                        })
                # Generic link pattern for their job cards
                if not jobs:
                    for m in re.finditer(
                        r'<a[^>]+href="(/jobs/\d+[^"]*)"[^>]*class="[^"]*job[^"]*"',
                        html, re.IGNORECASE,
                    ):
                        href    = m.group(1).strip()
                        job_url = f"https://jobs.accaglobal.com{href}"
                        if job_url not in seen:
                            seen.add(job_url)
                            jobs.append({
                                "title": role, "company": "ACCA Listed",
                                "location": location or "", "url": job_url,
                                "description": "", "tags": ["finance"], "source": "acca_global",
                            })
            if jobs:
                break
        except Exception:
            continue

    # RSS fallback (endpoint was returning 202 empty but may work with params)
    if not jobs:
        for rss_url in [
            f"https://jobs.accaglobal.com/jobs/rss/?keywords={role_q}&location={loc_q}",
            f"https://jobs.accaglobal.com/jobs.rss?keywords={role_q}",
        ]:
            try:
                resp = await client.get(rss_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
                if resp.status_code == 200 and ("<rss" in resp.text or "<feed" in resp.text):
                    root = ET.fromstring(resp.content)
                    for item in root.findall(".//item"):
                        title_el = item.find("title")
                        link_el  = item.find("link")
                        desc_el  = item.find("description")
                        if title_el is None or link_el is None:
                            continue
                        url   = (link_el.text or "").strip()
                        title = (title_el.text or "").strip()
                        if not url or url in seen:
                            continue
                        seen.add(url)
                        desc_raw = (desc_el.text or "") if desc_el is not None else ""
                        desc     = re.sub(r'<[^>]+>', ' ', desc_raw).strip()[:800]
                        jobs.append({
                            "title": title, "company": "ACCA Listed",
                            "location": location or "", "url": url,
                            "description": desc, "tags": [], "source": "acca_global",
                        })
                    if jobs:
                        break
            except Exception:
                continue

    return jobs[:15]


_BLOCK_PAT = re.compile(
    r'<script[^>]+type=[^>]*application/ld\+json[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


async def _fetch_trabajo_pk(
    client: httpx.AsyncClient, role: str, location: str
) -> list[dict]:
    """pk.trabajo.org — Pakistan job aggregator. Parses ItemList JSON-LD structure."""
    jobs: list[dict] = []
    seen: set[str]   = set()

    role_slug = role.lower().replace(" ", "-")

    # Their search URL pattern
    search_urls = [
        f"https://pk.trabajo.org/jobs-{role_slug}",
        f"https://pk.trabajo.org/?s={role.replace(' ', '+')}",
    ]

    for search_url in search_urls:
        try:
            resp = await client.get(search_url, headers=_BROWSER_HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            html = resp.text

            # Trabajo PK embeds jobs as Schema.org ItemList (not JobPosting)
            for block in _BLOCK_PAT.findall(html):
                try:
                    data = json.loads(block.strip())
                except Exception:
                    continue
                if not isinstance(data, dict) or data.get("@type") != "ItemList":
                    continue
                for item in (data.get("itemListElement") or []):
                    if not isinstance(item, dict):
                        continue
                    job_url = item.get("url", "")
                    title   = item.get("name", "")
                    if not job_url or job_url in seen or not title:
                        continue
                    seen.add(job_url)
                    jobs.append({
                        "title":       title,
                        "company":     "",
                        "location":    location or "Pakistan",
                        "url":         job_url,
                        "description": "",
                        "tags":        [],
                        "source":      "trabajo_pk",
                    })
            if jobs:
                break
        except Exception:
            continue

    return jobs[:20]


async def _fetch_bebee(
    client: httpx.AsyncClient, role: str, location: str
) -> list[dict]:
    """Bebee — professional network. Parses ItemList JSON-LD with 10k+ Pakistan jobs."""
    jobs: list[dict] = []
    seen: set[str]   = set()

    search_url = f"https://bebee.com/pk/jobs?q={role.replace(' ', '+')}"

    try:
        resp = await client.get(search_url, headers=_BROWSER_HEADERS, timeout=12)
        if resp.status_code != 200:
            return jobs
        html = resp.text

        # Bebee embeds jobs as JSON array of LD blocks. One block is an ItemList of job URLs.
        for block in _BLOCK_PAT.findall(html):
            try:
                raw = json.loads(block.strip())
            except Exception:
                continue
            items_to_check = raw if isinstance(raw, list) else [raw]
            for obj in items_to_check:
                if not isinstance(obj, dict) or obj.get("@type") != "ItemList":
                    continue
                for list_item in (obj.get("itemListElement") or []):
                    if not isinstance(list_item, dict):
                        continue
                    job_url = list_item.get("url", "")
                    if not job_url or job_url in seen:
                        continue
                    seen.add(job_url)
                    # Derive title from slug: "role-company-city--country-uuid"
                    slug = job_url.rstrip("/").split("/")[-1]
                    slug = re.sub(r'-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', '', slug, flags=re.IGNORECASE)
                    slug = re.sub(r'--[a-z]{2}-[a-z]{2}$', '', slug)
                    title = slug.replace("-", " ").title()[:100]
                    jobs.append({
                        "title":       title,
                        "company":     "",
                        "location":    location or "Pakistan",
                        "url":         job_url,
                        "description": "",
                        "tags":        [],
                        "source":      "bebee",
                    })
                if jobs:
                    break
            if jobs:
                break
    except Exception:
        pass

    return jobs[:15]


async def _fetch_joinimagine(
    client: httpx.AsyncClient, role: str, location: str
) -> list[dict]:
    """Join Imagine — startup jobs board. Scrapes company pages for actual job listings."""
    jobs: list[dict] = []
    seen: set[str]   = set()
    role_q = role.replace(" ", "+")

    # Try their direct job search endpoint first
    search_urls = [
        f"https://jobs.joinimagine.com/jobs?search={role_q}",
        f"https://jobs.joinimagine.com/jobs?q={role_q}",
        f"https://jobs.joinimagine.com/search?q={role_q}",
    ]

    company_links: list[str] = []

    for search_url in search_urls:
        try:
            resp = await client.get(search_url, headers=_BROWSER_HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            html = resp.text

            # JSON-LD job listings
            ld_jobs = _extract_jsonld_jobs(html, "joinimagine", search_url)
            for j in ld_jobs:
                if j["url"] not in seen:
                    seen.add(j["url"])
                    jobs.append(j)

            if jobs:
                break

            # Collect company page links to scrape individually
            for m in re.finditer(
                r'<a[^>]+href="(https?://jobs\.joinimagine\.com/companies/[^/"]+/?)"',
                html, re.IGNORECASE,
            ):
                link = m.group(1).strip().rstrip("/")
                if link not in seen:
                    seen.add(link)
                    company_links.append(link)
        except Exception:
            continue

    # Fallback: get company list then scrape each company's jobs page
    if not jobs:
        if not company_links:
            try:
                resp = await client.get("https://jobs.joinimagine.com/companies/", headers=_BROWSER_HEADERS, timeout=12)
                if resp.status_code == 200:
                    for m in re.finditer(
                        r'<a[^>]+href="(https?://jobs\.joinimagine\.com/companies/[^/"]+/?)"',
                        resp.text, re.IGNORECASE,
                    ):
                        link = m.group(1).strip().rstrip("/")
                        if link not in seen:
                            seen.add(link)
                            company_links.append(link)
            except Exception:
                pass

        # Scrape each company's jobs page (up to 6 companies)
        tasks = [
            client.get(f"{comp}/jobs", headers=_BROWSER_HEADERS, timeout=10)
            for comp in company_links[:6]
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for comp_url, resp in zip(company_links[:6], responses):
            if isinstance(resp, Exception) or resp.status_code != 200:
                continue
            html = resp.text
            ld_jobs = _extract_jsonld_jobs(html, "joinimagine", comp_url)
            for j in ld_jobs:
                if j["url"] not in seen:
                    seen.add(j["url"])
                    jobs.append(j)
            # Also look for job links
            for m in re.finditer(
                r'<a[^>]+href="(https?://jobs\.joinimagine\.com/[^"]+/jobs/[^"]+)"[^>]*>\s*([^<]{5,120})\s*</a>',
                html, re.IGNORECASE,
            ):
                url_found = m.group(1).strip()
                title     = re.sub(r'\s+', ' ', m.group(2)).strip()
                if url_found not in seen and len(title) > 4:
                    seen.add(url_found)
                    company_name = comp_url.rstrip("/").split("/")[-1].replace("-", " ").title()
                    jobs.append({
                        "title": title, "company": company_name,
                        "location": location or "", "url": url_found,
                        "description": "", "tags": [], "source": "joinimagine",
                    })
            if len(jobs) >= 15:
                break

    return jobs[:15]


async def _fetch_interviewpal(
    client: httpx.AsyncClient, role: str, location: str
) -> list[dict]:
    """InterviewPal — job board. Tries API endpoint and embedded JSON in page."""
    jobs: list[dict] = []
    seen: set[str]   = set()

    role_q = role.replace(" ", "+")
    loc_lower = location.lower() if location else ""
    is_remote = loc_lower in ("remote", "anywhere", "worldwide", "")

    # Try their API endpoint
    try:
        api_params: dict = {"q": role, "limit": 20}
        if not is_remote:
            api_params["location"] = location
        resp = await client.get(
            "https://www.interviewpal.com/api/jobs",
            params=api_params,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=12,
        )
        if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
            data = resp.json()
            for item in (data.get("jobs") or data.get("results") or data if isinstance(data, list) else []):
                if not isinstance(item, dict):
                    continue
                job_url = item.get("url") or item.get("apply_url") or item.get("link", "")
                if not job_url or job_url in seen:
                    continue
                seen.add(job_url)
                jobs.append({
                    "title":       item.get("title") or item.get("name", ""),
                    "company":     item.get("company") or item.get("company_name", ""),
                    "location":    item.get("location") or (location or ""),
                    "url":         job_url,
                    "description": (item.get("description") or "")[:800],
                    "tags":        [],
                    "source":      "interviewpal",
                })
    except Exception:
        pass

    # Fallback: scrape their jobs page
    if not jobs:
        search_url = f"https://www.interviewpal.com/jobs/?search={role_q}"
        if not is_remote:
            search_url += f"&location={location.replace(' ', '+')}"
        try:
            resp = await client.get(search_url, headers=_BROWSER_HEADERS, timeout=12)
            if resp.status_code == 200:
                html = resp.text

                # JSON-LD
                ld_jobs = _extract_jsonld_jobs(html, "interviewpal", search_url)
                for j in ld_jobs:
                    if j["url"] not in seen:
                        seen.add(j["url"])
                        jobs.append(j)

                # Look for embedded JSON state (React/Next.js __NEXT_DATA__)
                if not jobs:
                    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
                    if m:
                        try:
                            next_data = json.loads(m.group(1))
                            page_props = next_data.get("props", {}).get("pageProps", {})
                            for item in (page_props.get("jobs") or page_props.get("listings") or []):
                                if not isinstance(item, dict):
                                    continue
                                job_url = item.get("url") or item.get("applyUrl", "")
                                if not job_url:
                                    slug = item.get("slug") or item.get("id", "")
                                    job_url = f"https://www.interviewpal.com/jobs/{slug}" if slug else ""
                                if not job_url or job_url in seen:
                                    continue
                                seen.add(job_url)
                                jobs.append({
                                    "title":       item.get("title") or item.get("name", ""),
                                    "company":     item.get("company") or item.get("companyName", ""),
                                    "location":    item.get("location") or (location or ""),
                                    "url":         job_url,
                                    "description": (item.get("description") or "")[:800],
                                    "tags":        [],
                                    "source":      "interviewpal",
                                })
                        except Exception:
                            pass

                # Generic link fallback
                if not jobs:
                    for m in re.finditer(
                        r'<a[^>]+href="(https?://www\.interviewpal\.com/jobs/[^"]+)"[^>]*>\s*([^<]{5,120})\s*</a>',
                        html, re.IGNORECASE,
                    ):
                        url   = m.group(1).strip()
                        title = re.sub(r'\s+', ' ', m.group(2)).strip()
                        if url not in seen and len(title) > 4:
                            seen.add(url)
                            jobs.append({
                                "title": title, "company": "", "location": location or "",
                                "url": url, "description": "", "tags": [], "source": "interviewpal",
                            })
        except Exception:
            pass

    return jobs[:15]


# ── Main scraper ──────────────────────────────────────────────────────────────

async def _verify_urls(jobs: list[dict], client: httpx.AsyncClient, limit: int = 20) -> list[dict]:
    """
    HEAD-check job URLs and remove dead ones (404/410/gone).
    Only checks jobs that have a URL. Skips check if URL is empty.
    Processes up to `limit` jobs to keep latency reasonable.
    """
    async def _check(job: dict) -> dict | None:
        url = job.get("url", "")
        if not url:
            return job  # no URL — keep but can't verify
        try:
            r = await client.head(url, timeout=5, follow_redirects=True)
            if r.status_code in (404, 410, 400):
                return None  # dead link
            return job
        except Exception:
            return job  # network error — keep (don't discard on timeout)

    to_check = jobs[:limit]
    rest     = jobs[limit:]
    checked  = await asyncio.gather(*[_check(j) for j in to_check])
    return [j for j in checked if j is not None] + rest


async def job_scraper_impl(skills_json: str, location: str, role_preference: str) -> str:
    """
    Search jobs via Google Jobs (SerpAPI primary) + 16 free/direct boards.

    Priority order:
      1. SerpAPI Google Jobs (covers LinkedIn/Indeed/Glassdoor) — set SERP_API_KEY
      2. Location-aware boards: Arbeitnow, Findwork, Jobicy, The Muse, Adzuna
      3. Pakistan/onsite boards: Rozee.pk (20 jobs), Brightspyre (20 jobs),
         pk.trabajo.org (20 jobs), Bebee (15 jobs)
      4. Remote-only boards (RemoteOK, Remotive, WWR) — only for remote searches

    Location: ALWAYS from UI input — never from resume.
    Geocoding: Nominatim (free, no API key) for universal city/country/state support.
    """
    skills: list[str] = json.loads(skills_json) if skills_json else []
    search_terms = _build_search_terms(role_preference, skills)

    # Optional API keys from environment
    serp_key   = os.getenv("SERP_API_KEY", "")
    adzuna_id  = os.getenv("ADZUNA_APP_ID", "")
    adzuna_key = os.getenv("ADZUNA_APP_KEY", "")

    async with httpx.AsyncClient(follow_redirects=True) as client:

        # ── STEP 1: Universal location resolution ──────────────────────────────
        if _is_remote_input(location):
            loc_info = _expand_location(location)
        else:
            region = _check_region(location)
            if region:
                loc_info = region
            else:
                geo      = await _geocode_nominatim(location, client)
                loc_info = _build_loc_info(location, geo)

        is_remote_search = loc_info["is_remote"]
        primary_loc = loc_info["search_terms"][0] if not is_remote_search else "Remote"

        # ── STEP 2: Location-specific sources ────────────────────────────────
        # For remote searches: query with "Remote" only — never empty (avoids onsite bleed)
        # For location searches: query with user location + also empty (broader fallback)
        loc_tasks = [
            # Pakistan/onsite-focused boards first — highest-quality location-specific results
            _fetch_rozee(client, role_preference, primary_loc),
            _fetch_smartrecruiters(client, role_preference, primary_loc),
            _fetch_trabajo_pk(client, role_preference, primary_loc),
            _fetch_bebee(client, role_preference, primary_loc),
            _fetch_bayt(client, role_preference, primary_loc),
            _fetch_acca_global(client, role_preference, primary_loc),
            _fetch_joinimagine(client, role_preference, primary_loc),
            _fetch_interviewpal(client, role_preference, primary_loc),
            # International boards (may include Pakistan + global results)
            _fetch_arbeitnow(client, role_preference, primary_loc),
            _fetch_findwork(client, role_preference, primary_loc),
            _fetch_jobicy(client, role_preference, primary_loc),
            _fetch_themuse(client, role_preference, primary_loc),
        ]
        # NOTE: No empty-location fallback pass — would flood pool with global/remote jobs
        # that all fail the location filter anyway.

        # Google Jobs (SerpAPI) — primary source, single call with loc_info (handles all 3 variants internally)
        if serp_key:
            loc_tasks.append(_fetch_serpapi(client, role_preference, loc_info, serp_key))

        if adzuna_id and adzuna_key:
            loc_tasks.append(_fetch_adzuna(client, role_preference, loc_info, adzuna_id, adzuna_key))

        # ── STEP 3: Remote-only boards — SKIP for non-remote searches ────────────
        # RemoteOK / Remotive / WWR only return "Remote" location jobs.
        # For city/country searches those ALL get filtered out anyway — don't fetch.
        if is_remote_search:
            remote_tasks = [
                _fetch_remoteok(client, search_terms),
                _fetch_remotive(client, role_preference, skills),
                _fetch_weworkremotely(client, role_preference, skills),
            ]
            all_results = await asyncio.gather(
                asyncio.gather(*loc_tasks, return_exceptions=True),
                asyncio.gather(*remote_tasks, return_exceptions=True),
            )
            loc_results    = all_results[0]
            remote_results = all_results[1]
        else:
            loc_results    = await asyncio.gather(*loc_tasks, return_exceptions=True)
            remote_results = []

        # ── STEP 4: Merge ────────────────────────────────────────────────────────
        def _flatten(results) -> list[dict]:
            out = []
            for r in results:
                if isinstance(r, list):
                    out.extend(r)
            return out

        loc_jobs    = _flatten(loc_results)
        remote_jobs = _flatten(remote_results)

        # Merge with deduplication — location-specific first
        all_jobs: list[dict] = []
        seen_urls: set[str] = set()

        def _add_jobs(jobs_list: list[dict]):
            for job in jobs_list:
                url = job.get("url", "")
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)
                all_jobs.append(job)

        _add_jobs(loc_jobs)
        _add_jobs(remote_jobs)

        # ── STEP 5: Verify top job URLs (HEAD check) ────────────────────────────
        all_jobs = await _verify_urls(all_jobs, client, limit=30)

    return json.dumps({
        "success": True,
        "jobs": all_jobs[:200],
        "count": len(all_jobs[:200]),
        "loc_info": loc_info,
        "location_expanded": loc_info["search_terms"],
    })


@function_tool
async def job_scraper_tool(skills_json: str, location: str, role_preference: str) -> str:
    """
    Search job listings across 16+ sources simultaneously.

    Always active (no API key needed):
      Rozee.pk · Brightspyre · pk.trabajo.org · Bebee (Pakistan/onsite)
      Arbeitnow · Findwork · Jobicy · The Muse (international)
      RemoteOK · Remotive · We Work Remotely (remote searches only)

    Optional (set env vars):
      SERP_API_KEY     → Google Jobs (LinkedIn, Indeed, Glassdoor, Rozee.pk)
      ADZUNA_APP_ID + ADZUNA_APP_KEY → Adzuna
    """
    return await job_scraper_impl(
        skills_json=skills_json, location=location, role_preference=role_preference,
    )
