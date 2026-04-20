"""form_filler_tool — Fill job application forms on portal websites.

Uses Playwright to navigate to a job application page, detect form fields,
and fill them from candidate profile data.

Requires: pip install playwright && playwright install chromium
Requires valid session cookies from account_manager_tool.
"""
import json
from agents import function_tool


_FIELD_STRATEGIES = [
    # (css_selector_pattern, profile_field_key)
    ('input[name*="first"], input[placeholder*="First"]',     "first_name"),
    ('input[name*="last"], input[placeholder*="Last"]',       "last_name"),
    ('input[type="email"]',                                   "email"),
    ('input[name*="phone"], input[placeholder*="phone"]',     "phone"),
    ('input[name*="linkedin"]',                               "linkedin_url"),
    ('input[name*="github"]',                                 "github_url"),
    ('input[name*="website"], input[name*="portfolio"]',      "portfolio_url"),
    ('textarea[name*="cover"], textarea[placeholder*="cover"]', "cover_letter"),
    ('textarea[name*="summary"], textarea[name*="about"]',    "summary"),
]


async def form_filler_impl(
    job_url: str,
    profile_json: str,
    cookies_json: str,
    resume_path: str = "",
    headless: bool = True,
) -> str:
    """
    Navigate to a job application page and fill out the form.

    profile_json fields:
      first_name, last_name, email, phone, linkedin_url, github_url,
      portfolio_url, cover_letter, summary
    cookies_json: session cookies from account_manager_tool.
    """
    profile: dict = json.loads(profile_json)
    cookies: list = json.loads(cookies_json)

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=headless)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )

            # Restore session cookies
            if cookies:
                await context.add_cookies(cookies)

            page = await context.new_page()
            await page.goto(job_url, timeout=30_000)
            await page.wait_for_load_state("networkidle", timeout=15_000)

            filled_fields: list[str] = []
            errors: list[str] = []

            # Fill each known field type
            for selector, key in _FIELD_STRATEGIES:
                value = profile.get(key, "")
                if not value:
                    continue
                try:
                    elements = page.locator(selector)
                    if await elements.count() > 0:
                        await elements.first.fill(str(value))
                        filled_fields.append(key)
                except Exception as e:
                    errors.append(f"{key}: {e}")

            # Attach resume if path provided and file input exists
            if resume_path:
                try:
                    file_inputs = page.locator('input[type="file"]')
                    if await file_inputs.count() > 0:
                        await file_inputs.first.set_input_files(resume_path)
                        filled_fields.append("resume")
                except Exception as e:
                    errors.append(f"resume_upload: {e}")

            await browser.close()

        return json.dumps({
            "success":       True,
            "filled_fields": filled_fields,
            "errors":        errors,
            "job_url":       job_url,
        })

    except ImportError:
        return json.dumps({
            "success": False,
            "error": "Playwright not installed. Run: pip install playwright && playwright install chromium",
        })
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)})


@function_tool
async def form_filler_tool(
    job_url: str,
    profile_json: str,
    cookies_json: str,
    resume_path: str = "",
    headless: bool = True,
) -> str:
    """Fill a job application form on a portal website.

    profile_json: JSON object with candidate details (first_name, last_name,
      email, phone, linkedin_url, cover_letter, etc.).
    cookies_json: session cookies from account_manager_tool (JSON array).
    resume_path: absolute path to resume file for file-upload fields.
    """
    return await form_filler_impl(
        job_url=job_url, profile_json=profile_json,
        cookies_json=cookies_json, resume_path=resume_path,
        headless=headless,
    )
