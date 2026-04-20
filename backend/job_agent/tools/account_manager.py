"""account_manager_tool — Manage portal account login sessions.

Handles portal authentication using credentials from credential_vault.
Stores resulting session cookies via session_manager for reuse.

NOTE: Browser automation (Playwright) must be installed separately.
Install: pip install playwright && playwright install chromium

This module provides the automation scaffold. Active browser login is
initiated only when a valid session does not already exist.
"""
import json
from agents import function_tool
from .credential_vault import vault_retrieve_impl
from .session_manager import session_load_impl, session_save_impl


async def account_login_impl(
    user_id: str,
    portal_name: str,
    headless: bool = True,
) -> str:
    """
    Login to a portal using stored credentials.

    Flow:
      1. Check session_manager for a valid existing session.
      2. If found → return cached cookies (no new login).
      3. If not found → retrieve credentials from vault → launch browser → login.
      4. Save new session cookies to session_manager.
    """
    # Step 1: Try cached session
    session_result = json.loads(await session_load_impl(user_id=user_id, portal_name=portal_name))
    if session_result.get("found"):
        return json.dumps({
            "success":      True,
            "portal_name":  portal_name,
            "source":       "cached_session",
            "cookies":      session_result["cookies"],
        })

    # Step 2: Retrieve credentials
    creds_result = json.loads(await vault_retrieve_impl(user_id=user_id, portal_name=portal_name))
    if not creds_result.get("success"):
        return json.dumps({
            "success": False,
            "error": f"No credentials stored for {portal_name}. Add them via credential_vault first.",
        })

    portal_url = creds_result["portal_url"]
    username   = creds_result["username"]
    password   = creds_result["password"]

    # Step 3: Browser automation
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser  = await pw.chromium.launch(headless=headless)
            context  = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page     = await context.new_page()

            await page.goto(portal_url, timeout=30_000)

            # Generic login — portal-specific selectors can be extended here
            await page.fill('input[type="email"], input[name="email"], input[name="username"]', username)
            await page.fill('input[type="password"]', password)
            await page.click('button[type="submit"], input[type="submit"]')
            await page.wait_for_load_state("networkidle", timeout=15_000)

            cookies = await context.cookies()
            await browser.close()

        # Step 4: Cache the session
        await session_save_impl(user_id=user_id, portal_name=portal_name, cookies=cookies)

        return json.dumps({
            "success":     True,
            "portal_name": portal_name,
            "source":      "fresh_login",
            "cookies":     cookies,
        })

    except ImportError:
        return json.dumps({
            "success": False,
            "error": "Playwright not installed. Run: pip install playwright && playwright install chromium",
        })
    except Exception as exc:
        return json.dumps({"success": False, "error": f"Login failed: {exc}"})


@function_tool
async def account_manager_tool(
    user_id: str,
    portal_name: str,
    headless: bool = True,
) -> str:
    """Log in to a job portal using stored credentials.

    Returns session cookies for use in subsequent portal operations.
    Reuses cached session if still valid (no unnecessary logins).
    Credentials must be pre-stored via credential_vault_store.
    """
    return await account_login_impl(
        user_id=user_id, portal_name=portal_name, headless=headless
    )
