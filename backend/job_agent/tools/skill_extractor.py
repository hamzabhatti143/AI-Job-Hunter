"""STEP 2 — Universal resume skill, role, location and experience extractor."""
import re
import json
from agents import function_tool

# ── Skills ────────────────────────────────────────────────────────────────────
# Each entry: (display_name, match_pattern, use_word_boundary)
# Word boundary is used for short/common words to avoid false matches.
SKILLS_DB = [
    # Languages
    ("Python",        "python",        True),
    ("JavaScript",    "javascript",    False),
    ("TypeScript",    "typescript",    False),
    ("Java",          "java",          True),
    ("C#",            r"c#",           False),
    ("C++",           r"c\+\+",        False),
    ("Rust",          "rust",          True),
    ("Go",            r"\bgo\b(?!ogle|ogl|od|al|t)", False),  # Go but not Google/Good/Got
    ("Ruby",          "ruby",          True),
    ("PHP",           r"\bphp\b",      False),
    ("Swift",         "swift",         True),
    ("Kotlin",        "kotlin",        True),
    ("Scala",         "scala",         True),
    ("R",             r"\bR\b",        False),
    ("Dart",          "dart",          True),
    ("Solidity",      "solidity",      True),
    ("Bash",          r"\bbash\b",     False),
    ("Shell",         r"\bshell\b",    False),
    ("MATLAB",        "matlab",        True),
    ("Perl",          r"\bperl\b",     False),

    # Frontend
    ("React",         r"\breact\b",    False),
    ("Next.js",       r"next\.js",     False),
    ("Vue",           r"\bvue\b",      False),
    ("Angular",       "angular",       True),
    ("Svelte",        "svelte",        True),
    ("HTML",          r"\bhtml\b",     False),
    ("CSS",           r"\bcss\b",      False),
    ("Tailwind CSS",  "tailwind",      False),
    ("Sass",          r"\bsass\b",     False),
    ("Redux",         "redux",         True),
    ("jQuery",        "jquery",        True),
    ("Webpack",       "webpack",       True),
    ("Vite",          r"\bvite\b",     False),

    # Backend / APIs
    ("Node.js",       r"node\.js",     False),
    ("Express",       "express",       True),
    ("FastAPI",       "fastapi",       False),
    ("Django",        "django",        True),
    ("Flask",         r"\bflask\b",    False),
    ("Spring Boot",   "spring boot",   False),
    ("Spring",        r"\bspring\b",   False),
    ("Laravel",       "laravel",       True),
    ("GraphQL",       "graphql",       False),
    ("REST API",      r"rest\s*api",   False),
    ("gRPC",          r"\bgrpc\b",     False),
    ("WebSocket",     "websocket",     False),

    # Databases
    ("PostgreSQL",    "postgresql",    False),
    ("MySQL",         "mysql",         False),
    ("MongoDB",       "mongodb",       False),
    ("Redis",         "redis",         True),
    ("SQLite",        "sqlite",        False),
    ("Elasticsearch", "elasticsearch", False),
    ("DynamoDB",      "dynamodb",      False),
    ("Cassandra",     "cassandra",     True),
    ("Supabase",      "supabase",      True),
    ("Firebase",      "firebase",      True),
    ("SQL",           r"\bsql\b",      False),

    # Cloud & DevOps
    ("AWS",           r"\baws\b",      False),
    ("Azure",         r"\bazure\b",    False),
    ("GCP",           r"\bgcp\b",      False),
    ("Google Cloud",  "google cloud",  False),
    ("Docker",        "docker",        True),
    ("Kubernetes",    "kubernetes",    False),
    ("Terraform",     "terraform",     True),
    ("CI/CD",         r"ci[/\-]?cd",  False),
    ("GitHub Actions","github actions",False),
    ("Jenkins",       "jenkins",       True),
    ("Nginx",         "nginx",         True),
    ("Linux",         r"\blinux\b",    False),
    ("Microservices", "microservices", False),
    ("Ansible",       "ansible",       True),
    ("Helm",          r"\bhelm\b",     False),
    ("Vercel",        "vercel",        True),
    ("Netlify",       "netlify",       True),

    # AI / ML / Data
    ("Machine Learning", "machine learning", False),
    ("Deep Learning", "deep learning", False),
    ("NLP",           r"\bnlp\b",      False),
    ("PyTorch",       "pytorch",       False),
    ("TensorFlow",    "tensorflow",    False),
    ("Scikit-learn",  "scikit",        False),
    ("Pandas",        "pandas",        True),
    ("NumPy",         "numpy",         False),
    ("OpenAI",        "openai",        False),
    ("LangChain",     "langchain",     False),
    ("Hugging Face",  "hugging face",  False),
    ("Computer Vision","computer vision",False),
    ("LLM",           r"\bllm\b",      False),

    # Tools
    ("Git",           r"\bgit\b",      False),
    ("GitHub",        "github",        False),
    ("Figma",         "figma",         True),
    ("Jira",          "jira",          True),
    ("Notion",        "notion",        True),
    ("Postman",       "postman",       True),
    ("VS Code",       r"vs\s*code",    False),
    ("Linux",         r"\blinux\b",    False),
    ("Agile",         r"\bagile\b",    False),
    ("Scrum",         r"\bscrum\b",    False),
    ("Kafka",         "kafka",         True),
    ("RabbitMQ",      "rabbitmq",      False),

    # Design / Other
    ("UI/UX",         r"ui[/\-]ux",    False),
    ("Responsive Design", "responsive", False),
    ("SEO",           r"\bseo\b",      False),
    ("WordPress",     "wordpress",     False),
    ("Shopify",       "shopify",       True),
    ("Salesforce",    "salesforce",    True),
]

# ── Role keyword patterns ─────────────────────────────────────────────────────
# Ordered from most specific to least
ROLE_PATTERNS = [
    # Frontend
    r"front[\-\s]?end\s+(?:web\s+)?developer",
    r"frontend\s+(?:web\s+)?developer",
    r"ui\s+developer",
    r"react\s+developer",
    r"next\.js\s+developer",
    r"vue\.?js\s+developer",
    r"angular\s+developer",
    # Backend
    r"back[\-\s]?end\s+developer",
    r"backend\s+developer",
    r"python\s+developer",
    r"node\.?js\s+developer",
    r"django\s+developer",
    r"java\s+developer",
    r"php\s+developer",
    # Fullstack
    r"full[\-\s]?stack\s+(?:web\s+)?developer",
    r"fullstack\s+developer",
    # Mobile
    r"mobile\s+developer",
    r"ios\s+developer",
    r"android\s+developer",
    r"react\s+native\s+developer",
    r"flutter\s+developer",
    # Data / AI / ML
    r"data\s+scientist",
    r"data\s+analyst",
    r"data\s+engineer",
    r"machine\s+learning\s+engineer",
    r"ml\s+engineer",
    r"ai\s+engineer",
    r"nlp\s+engineer",
    r"research\s+scientist",
    # DevOps / Cloud
    r"devops\s+engineer",
    r"cloud\s+engineer",
    r"site\s+reliability\s+engineer",
    r"platform\s+engineer",
    r"infrastructure\s+engineer",
    r"systems\s+engineer",
    # Design
    r"ui[/\-]?ux\s+designer",
    r"product\s+designer",
    r"graphic\s+designer",
    r"web\s+designer",
    # General
    r"software\s+engineer",
    r"software\s+developer",
    r"web\s+developer",
    r"junior\s+\w+\s+developer",
    r"senior\s+\w+\s+developer",
    r"lead\s+\w+\s+developer",
    r"(?:junior|senior|lead|principal|staff)?\s*software\s+engineer",
    # Marketing / SEO
    r"seo\s+specialist",
    r"digital\s+marketing\s+(?:specialist|manager)",
    r"content\s+(?:writer|creator|strategist)",
    r"marketing\s+manager",
    # QA
    r"qa\s+engineer",
    r"test\s+engineer",
    r"quality\s+assurance",
    # PM
    r"product\s+manager",
    r"project\s+manager",
    r"scrum\s+master",
]

# ── Country/location patterns ─────────────────────────────────────────────────
PHONE_COUNTRY = {
    "+93": "Afghanistan", "+355": "Albania", "+213": "Algeria",
    "+376": "Andorra", "+244": "Angola", "+54": "Argentina",
    "+374": "Armenia", "+61": "Australia", "+43": "Austria",
    "+994": "Azerbaijan", "+880": "Bangladesh", "+375": "Belarus",
    "+32": "Belgium", "+501": "Belize", "+229": "Benin",
    "+975": "Bhutan", "+591": "Bolivia", "+387": "Bosnia",
    "+55": "Brazil", "+673": "Brunei", "+359": "Bulgaria",
    "+226": "Burkina Faso", "+257": "Burundi", "+855": "Cambodia",
    "+237": "Cameroon", "+1": "USA/Canada", "+236": "CAR",
    "+56": "Chile", "+86": "China", "+57": "Colombia",
    "+243": "Congo", "+506": "Costa Rica", "+385": "Croatia",
    "+53": "Cuba", "+357": "Cyprus", "+420": "Czech Republic",
    "+45": "Denmark", "+593": "Ecuador", "+20": "Egypt",
    "+503": "El Salvador", "+372": "Estonia", "+251": "Ethiopia",
    "+358": "Finland", "+33": "France", "+241": "Gabon",
    "+220": "Gambia", "+995": "Georgia", "+49": "Germany",
    "+233": "Ghana", "+30": "Greece", "+502": "Guatemala",
    "+509": "Haiti", "+504": "Honduras", "+36": "Hungary",
    "+354": "Iceland", "+91": "India", "+62": "Indonesia",
    "+98": "Iran", "+964": "Iraq", "+353": "Ireland",
    "+972": "Israel", "+39": "Italy", "+1876": "Jamaica",
    "+81": "Japan", "+962": "Jordan", "+7": "Kazakhstan",
    "+254": "Kenya", "+82": "South Korea", "+965": "Kuwait",
    "+996": "Kyrgyzstan", "+856": "Laos", "+371": "Latvia",
    "+961": "Lebanon", "+231": "Liberia", "+218": "Libya",
    "+370": "Lithuania", "+352": "Luxembourg", "+261": "Madagascar",
    "+265": "Malawi", "+60": "Malaysia", "+960": "Maldives",
    "+223": "Mali", "+356": "Malta", "+222": "Mauritania",
    "+230": "Mauritius", "+52": "Mexico", "+373": "Moldova",
    "+976": "Mongolia", "+212": "Morocco", "+258": "Mozambique",
    "+95": "Myanmar", "+264": "Namibia", "+977": "Nepal",
    "+31": "Netherlands", "+64": "New Zealand", "+505": "Nicaragua",
    "+227": "Niger", "+234": "Nigeria", "+47": "Norway",
    "+968": "Oman", "+92": "Pakistan", "+507": "Panama",
    "+675": "Papua New Guinea", "+595": "Paraguay", "+51": "Peru",
    "+63": "Philippines", "+48": "Poland", "+351": "Portugal",
    "+974": "Qatar", "+40": "Romania", "+7": "Russia",
    "+250": "Rwanda", "+966": "Saudi Arabia", "+221": "Senegal",
    "+381": "Serbia", "+232": "Sierra Leone", "+65": "Singapore",
    "+421": "Slovakia", "+386": "Slovenia", "+252": "Somalia",
    "+27": "South Africa", "+34": "Spain", "+94": "Sri Lanka",
    "+249": "Sudan", "+268": "Swaziland", "+46": "Sweden",
    "+41": "Switzerland", "+963": "Syria", "+886": "Taiwan",
    "+992": "Tajikistan", "+255": "Tanzania", "+66": "Thailand",
    "+216": "Tunisia", "+90": "Turkey", "+993": "Turkmenistan",
    "+256": "Uganda", "+380": "Ukraine", "+971": "UAE",
    "+44": "UK", "+1": "USA", "+598": "Uruguay",
    "+998": "Uzbekistan", "+58": "Venezuela", "+84": "Vietnam",
    "+967": "Yemen", "+260": "Zambia", "+263": "Zimbabwe",
}

CITY_COUNTRY = {
    # Pakistan
    "karachi": "Pakistan", "lahore": "Pakistan", "islamabad": "Pakistan",
    "rawalpindi": "Pakistan", "faisalabad": "Pakistan", "multan": "Pakistan",
    "peshawar": "Pakistan", "quetta": "Pakistan",
    # India
    "mumbai": "India", "delhi": "India", "bangalore": "India",
    "hyderabad": "India", "chennai": "India", "kolkata": "India",
    "pune": "India", "ahmedabad": "India", "jaipur": "India",
    # USA
    "new york": "USA", "san francisco": "USA", "los angeles": "USA",
    "chicago": "USA", "seattle": "USA", "austin": "USA",
    "boston": "USA", "denver": "USA", "miami": "USA",
    # UK
    "london": "UK", "manchester": "UK", "birmingham": "UK",
    "glasgow": "UK", "edinburgh": "UK",
    # Canada
    "toronto": "Canada", "vancouver": "Canada", "montreal": "Canada",
    "calgary": "Canada", "ottawa": "Canada",
    # Germany
    "berlin": "Germany", "munich": "Germany", "hamburg": "Germany",
    "frankfurt": "Germany", "cologne": "Germany",
    # UAE
    "dubai": "UAE", "abu dhabi": "UAE", "sharjah": "UAE",
    # Others
    "sydney": "Australia", "melbourne": "Australia",
    "amsterdam": "Netherlands", "paris": "France",
    "singapore": "Singapore", "tokyo": "Japan",
    "toronto": "Canada", "zurich": "Switzerland",
    "stockholm": "Sweden", "oslo": "Norway",
    "nairobi": "Kenya", "lagos": "Nigeria", "cairo": "Egypt",
    "istanbul": "Turkey", "athens": "Greece",
    "warsaw": "Poland", "prague": "Czech Republic",
    "manila": "Philippines", "jakarta": "Indonesia",
    "kuala lumpur": "Malaysia", "bangkok": "Thailand",
}

COUNTRY_NAMES = [
    "afghanistan", "albania", "algeria", "argentina", "armenia", "australia",
    "austria", "azerbaijan", "bangladesh", "belarus", "belgium", "brazil",
    "bulgaria", "cambodia", "cameroon", "canada", "chile", "china",
    "colombia", "croatia", "czech republic", "denmark", "egypt",
    "ethiopia", "finland", "france", "germany", "ghana", "greece",
    "hungary", "india", "indonesia", "iran", "iraq", "ireland",
    "israel", "italy", "japan", "jordan", "kazakhstan", "kenya",
    "south korea", "kuwait", "kyrgyzstan", "lebanon", "libya",
    "malaysia", "maldives", "mali", "mexico", "morocco", "mozambique",
    "myanmar", "nepal", "netherlands", "new zealand", "nigeria", "norway",
    "oman", "pakistan", "peru", "philippines", "poland", "portugal",
    "qatar", "romania", "russia", "rwanda", "saudi arabia", "senegal",
    "singapore", "south africa", "spain", "sri lanka", "sudan", "sweden",
    "switzerland", "syria", "taiwan", "tanzania", "thailand", "tunisia",
    "turkey", "ukraine", "uae", "united arab emirates",
    "united kingdom", "united states", "usa", "uk", "uruguay",
    "uzbekistan", "venezuela", "vietnam", "yemen", "zambia", "zimbabwe",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_skills(text: str) -> list[str]:
    """Match skills from SKILLS_DB against resume text."""
    text_lower = text.lower()
    found = []
    seen = set()
    for display, pattern, boundary in SKILLS_DB:
        if boundary:
            pat = r'\b' + pattern + r'\b'
        else:
            pat = pattern
        if re.search(pat, text_lower, re.IGNORECASE):
            key = display.lower()
            if key not in seen:
                seen.add(key)
                found.append(display)
    return found


def _extract_role(text: str) -> str:
    """
    Detect the candidate's primary role from the resume.
    Searches top section first, then anywhere in document.
    Returns a clean searchable role string.
    """
    # Search only top 20 lines first (header area)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    header = ' '.join(lines[:20])

    for pat in ROLE_PATTERNS:
        m = re.search(pat, header, re.IGNORECASE)
        if m:
            # Capitalise each word nicely
            return m.group(0).strip().title()

    # Search full text if not found in header
    for pat in ROLE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0).strip().title()

    # Last resort: look for a line in top 5 that looks like a job title
    for line in lines[:5]:
        if any(kw in line.lower() for kw in [
            'developer', 'engineer', 'designer', 'analyst',
            'manager', 'specialist', 'consultant', 'architect',
            'scientist', 'writer', 'marketer',
        ]):
            # Take first part only (before any | · separator)
            primary = re.split(r'\s*[|•·/,]\s*', line)[0].strip()
            if 2 < len(primary) < 60:
                return primary

    return ""


def _extract_location(text: str) -> str:
    """
    Detect candidate location from:
    1. Phone country code
    2. Known city/country names in resume header
    3. "City, Country" address pattern (top 400 chars only)
    """
    # 1. Phone prefix (most reliable — sort longest first for specificity)
    for prefix in sorted(PHONE_COUNTRY.keys(), key=len, reverse=True):
        if prefix in text:
            return PHONE_COUNTRY[prefix]

    # 2. City name in top 400 chars
    top = text[:400].lower()
    for city, country in CITY_COUNTRY.items():
        if re.search(r'\b' + re.escape(city) + r'\b', top):
            return f"{city.title()}, {country}"

    # 3. Country name in top 400 chars
    for country in COUNTRY_NAMES:
        if re.search(r'\b' + re.escape(country) + r'\b', top, re.IGNORECASE):
            return country.title()

    # 4. Address pattern only in header (first 300 chars), validated against known names
    header = text[:300]
    addr_match = re.search(
        r'\b([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})?),\s*([A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})?)\b',
        header
    )
    if addr_match:
        part2 = addr_match.group(2).lower().strip()
        # Second part must be a known country or state abbreviation
        if any(re.search(r'\b' + re.escape(c) + r'\b', part2) for c in COUNTRY_NAMES):
            return addr_match.group(0).strip()

    return ""


def _extract_experience(text: str) -> int:
    """
    Parse date ranges in the resume and return total years of experience.
    Handles formats: 'Jan 2023 - Mar 2025', '2020 – Present', 'March 2021 to Current'
    """
    MONTH_MAP = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'june': 6, 'july': 7, 'august': 8, 'september': 9,
        'october': 10, 'november': 11, 'december': 12,
    }
    CURRENT_YEAR, CURRENT_MONTH = 2026, 4
    month_pat = '|'.join(MONTH_MAP.keys())
    sep_pat = r'\s*[-–—to/]+\s*'
    present_pat = r'present|current|now|today|ongoing'

    # Pattern: "Month? Year – Month? Year/Present"
    pattern = re.compile(
        rf'(?:({month_pat})\s+)?(20\d{{2}}|19\d{{2}})'
        rf'{sep_pat}'
        rf'(?:({month_pat})\s+)?(20\d{{2}}|19\d{{2}}|{present_pat})',
        re.IGNORECASE
    )

    total_months = 0
    for m in pattern.finditer(text):
        sm = (m.group(1) or '').lower()[:3]
        sy = int(m.group(2))
        em = (m.group(3) or '').lower()[:3]
        ey_raw = (m.group(4) or '').lower()

        start_month = MONTH_MAP.get(sm, 1)
        if any(w in ey_raw for w in ['present', 'current', 'now', 'today', 'ongoing']):
            end_year, end_month = CURRENT_YEAR, CURRENT_MONTH
        else:
            try:
                end_year = int(ey_raw)
            except ValueError:
                continue
            end_month = MONTH_MAP.get(em, 12)

        months = (end_year - sy) * 12 + (end_month - start_month)
        if 0 < months < 600:
            total_months += months

    if total_months > 0:
        return max(1, round(total_months / 12))

    # Fallback: max year – min year
    years = sorted(set(int(y) for y in re.findall(r'\b((?:19|20)\d{2})\b', text)
                       if 1990 <= int(y) <= 2030))
    if len(years) >= 2:
        return years[-1] - years[0]
    return 0


def _extract_name(text: str) -> str:
    """Extract candidate name — first non-empty line if it looks like a name."""
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines[:3]:
        # A name: 2-4 words, each starting with capital, no digits/special chars
        if re.match(r'^[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){1,3}$', line):
            return line
    return "Candidate"


# ── Main ──────────────────────────────────────────────────────────────────────

async def skill_extractor_impl(resume_text: str) -> str:
    name = _extract_name(resume_text)
    role = _extract_role(resume_text)
    location = _extract_location(resume_text)
    skills = _find_skills(resume_text)
    experience_years = _extract_experience(resume_text)

    email_m = re.search(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', resume_text)
    email = email_m.group(0) if email_m else None

    phone_m = re.search(r'(\+?\d[\d\s\-().]{7,}\d)', resume_text)
    phone = phone_m.group(0).strip() if phone_m else None

    return json.dumps({
        "success": True,
        "name": name,
        "email": email,
        "phone": phone,
        "role": role,
        "location": location,
        "skills": skills,
        "experience_years": experience_years,
    })


@function_tool
async def skill_extractor_tool(resume_text: str) -> str:
    """
    Universal resume extractor. Detects name, email, phone, role/position,
    location (city/country), skills, and years of experience from any resume format.
    """
    return await skill_extractor_impl(resume_text=resume_text)
