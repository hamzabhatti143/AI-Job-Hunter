"""STEP 7 — Generate a personalized cold email using OpenAI or Gemini."""
import os
import json
import httpx
from agents import function_tool
from openai import AsyncOpenAI

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"


def _detect_provider(api_key: str) -> str:
    """Detect which AI provider to use based on the key format."""
    if api_key.startswith("AIza"):
        return "gemini"
    if api_key.startswith("sk-"):
        return "openai"
    return "gemini"  # default to free Gemini if no key or unknown format


def _build_prompt(job: dict, skills: list, user_name: str, user_email: str, recruiter_name: str) -> str:
    greeting = f"Dear {recruiter_name}" if recruiter_name else "Dear Hiring Manager"
    top_skills = ", ".join(skills[:5])
    return f"""Write a professional cold email applying for the following job.

Job Title: {job.get('title', 'Software Engineer')}
Company: {job.get('company', 'the company')}
Matched Skills: {top_skills}
Candidate Name: {user_name}
Candidate Email: {user_email}

Requirements:
1. Start with "{greeting},"
2. Reference the specific role and company in the first sentence
3. Highlight 3-5 of the matched skills with concrete context
4. Include one clear call-to-action (request for interview or next step)
5. Professional closing with candidate name and email
6. Keep it under 250 words
7. Do NOT include any placeholder text — use the actual values provided

Return only the email body, no subject line."""


async def _call_gemini(prompt: str, api_key: str) -> str:
    """Call Gemini API directly via HTTP."""
    key = api_key if api_key.startswith("AIza") else GEMINI_API_KEY
    if not key:
        raise ValueError("No Gemini API key available")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            params={"key": key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


async def _call_openai(prompt: str, api_key: str) -> str:
    """Call OpenAI API."""
    client = AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=400,
    )
    return response.choices[0].message.content.strip()


async def email_writer_impl(
    job_json: str,
    skills_json: str,
    user_name: str,
    user_email: str,
    api_key: str,
    recruiter_email: str = "",
    recruiter_name: str = "",
) -> str:
    job: dict = json.loads(job_json)
    skills: list = json.loads(skills_json)
    prompt = _build_prompt(job, skills, user_name, user_email, recruiter_name)

    provider = _detect_provider(api_key)
    body = ""
    error_detail = ""

    # Primary provider
    try:
        if provider == "openai":
            body = await _call_openai(prompt, api_key)
        else:
            body = await _call_gemini(prompt, api_key)
    except Exception as e:
        error_detail = str(e)

    # Fallback: if OpenAI failed, try Gemini
    if not body and provider == "openai":
        try:
            body = await _call_gemini(prompt, "")
            error_detail = ""
        except Exception as e2:
            error_detail = f"OpenAI error: {error_detail} | Gemini fallback error: {e2}"

    if not body:
        return json.dumps({"success": False, "error": error_detail or "Failed to generate email"})

    subject = f"Application for {job.get('title', 'Position')} at {job.get('company', 'Your Company')}"
    return json.dumps({
        "success": True,
        "subject": subject,
        "body": body,
        "recipient": recruiter_email,
        "job_title": job.get("title"),
        "company": job.get("company"),
    })


@function_tool
async def email_writer_tool(
    job_json: str,
    skills_json: str,
    user_name: str,
    user_email: str,
    api_key: str,
    recruiter_email: str = "",
    recruiter_name: str = "",
) -> str:
    """Generate a personalized job application email.
    Supports OpenAI (sk-...) and Gemini (AIza...) keys.
    Falls back to Gemini automatically if OpenAI fails.
    Pass api_key='' to use the free Gemini plan.
    """
    return await email_writer_impl(
        job_json=job_json, skills_json=skills_json, user_name=user_name,
        user_email=user_email, api_key=api_key, recruiter_email=recruiter_email,
        recruiter_name=recruiter_name,
    )
