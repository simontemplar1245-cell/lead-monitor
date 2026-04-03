"""
Lead Monitor Configuration
==========================
All target communities, keywords, and settings in one place.
Tuned specifically for Advance AI Services - AI chatbots & AI phone receptionists.

STRATEGY: We target industry-specific communities where BUYERS are,
not tech communities where builders hang out. We search for PAIN POINTS
(missed calls, receptionist quit) not solution keywords (AI chatbot).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# API KEYS (loaded from .env file - NEVER hardcode these)
# =============================================================================
# Reddit uses public JSON endpoints - no API key or account needed
# Just needs a descriptive User-Agent string (Reddit requires this)
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "LeadMonitor/1.0 by AdvanceAIServices")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# =============================================================================
# SCANNING SCHEDULE
# =============================================================================
SCAN_INTERVAL_MINUTES = 30  # GitHub Actions runs every 30 mins
MAX_POSTS_PER_SUBREDDIT = 25  # per scan cycle
MAX_POSTS_PER_FORUM = 15  # forums are slower, smaller
LOOKBACK_HOURS = 1  # only look at posts from last hour (avoids duplicates)

# =============================================================================
# CLASSIFICATION THRESHOLDS
# =============================================================================
# Claude Haiku classifies leads as HOT (0.8-1.0), WARM (0.5-0.79), COLD (0-0.49)
HOT_THRESHOLD = 0.8
WARM_THRESHOLD = 0.5

# =============================================================================
# TARGET SUBREDDITS - Organized by priority tier
# =============================================================================
# TIER 1: Hidden gems - industry-specific, virtually zero AI marketing competition
# TIER 2: Good targets - some competition but high buyer intent
# TIER 3: Supplementary - larger communities, more noise but occasional gems

SUBREDDITS = {
    # =========================================================================
    # TIER 1: HIDDEN GEMS (Primary targets - check every scan)
    # =========================================================================
    "tier1": [
        # Trades / Blue-collar businesses (PERFECT for AI receptionist)
        "sweatystartup",       # ~118k - blue collar entrepreneurs, miss calls on jobs
        "pressurewashing",     # ~29k - small biz owners, very niche
        "lawncare",            # ~680k - mix but many biz owners, seasonal call spikes
        "Roofing",             # ~15k - contractors missing calls on roofs
        "CleaningService",     # ~5k - cleaning biz owners, scheduling problems
        "HomeImprovement",     # large but has contractor discussions

        # Dental
        "Dentistry",           # ~130k - practice owners, front desk problems

        # Legal
        "Lawyertalk",          # ~65k - solo/small firm lawyers, intake problems
        "LawFirm",            # smaller, business-of-law focused

        # Insurance
        "InsuranceAgent",      # ~10k - tiny but perfectly targeted

        # Real Estate
        "realtors",            # ~92k - agents, lead response anxiety

        # Salon/Beauty
        "hairstylist",         # ~11k - solo stylists, missed booking calls

        # Restaurant
        "restaurantowners",    # ~17k - small but real buyers
    ],

    # =========================================================================
    # TIER 2: GOOD TARGETS (Check every scan, more noise to filter)
    # =========================================================================
    "tier2": [
        # Trades (larger communities)
        "electricians",        # ~400k - many owner-operators
        "HVAC",                # ~155k - emergency after-hours call problem
        "plumbing",            # ~289k - emergency calls, missed jobs

        # Business/Entrepreneur (targeted searches only)
        "smallbusiness",       # ~1.5M - large, competitive but high volume
        "Entrepreneur",        # ~5.1M - very large, lots of noise

        # E-commerce (chatbot buyers)
        "ecommerce",           # ~200k - store owners needing chat support
        "shopify",             # ~200k - store owners

        # Accounting (seasonal pain)
        "Accounting",          # ~468k - tax season call overload

        # Veterinary
        "Veterinary",          # ~20k - vet practice owners
        "VetTech",             # ~30k - some practice management discussion

        # Medical/Health practices
        "Optometry",           # ~15k - practice owners
        "physicaltherapy",     # ~50k - clinic owners
    ],

    # =========================================================================
    # TIER 3: SUPPLEMENTARY (Check less frequently, high noise)
    # =========================================================================
    "tier3": [
        "SaaS",                # SaaS founders needing customer support
        "startups",            # early stage companies
        "freelance",           # freelancers building for clients
        "webdev",              # developers who build for clients
        "CustomerService",     # CS professionals looking for tools
        "VoIP",                # people looking for phone solutions
        "agency",              # digital marketing agencies
        "EntrepreneurRideAlong",  # people actively building businesses
    ]
}

# =============================================================================
# PAIN POINT KEYWORDS - What buyers ACTUALLY say (not solution keywords)
# =============================================================================
# These are organized by the PROBLEM the person is experiencing.
# Competitors search for "AI chatbot" - we search for the pain that makes
# someone NEED an AI chatbot.

PAIN_KEYWORDS = {
    # =========================================================================
    # MISSED CALLS / PHONE PROBLEMS (AI Receptionist triggers)
    # =========================================================================
    "missed_calls": [
        "missed calls",
        "missing calls",
        "miss calls",
        "missed a call",
        "can't answer the phone",
        "cant answer the phone",
        "can not answer the phone",
        "cannot answer the phone",
        "phone keeps ringing",
        "phone ringing",
        "too busy to answer",
        "calls go to voicemail",
        "going to voicemail",
        "voicemail is killing",
        "nobody to answer",
        "no one to answer the phone",
        "answer phones",
        "answering the phone",
        "phone coverage",
        "after hours calls",
        "after-hours calls",
        "nights and weekends",
        "emergency calls after hours",
        "weekend calls",
        "lost the job because",
        "customer went to competitor",
        "customers going to competitors",
        "lost a customer because",
        "losing customers because",
        "didn't answer in time",
    ],

    # =========================================================================
    # RECEPTIONIST / FRONT DESK PROBLEMS
    # =========================================================================
    "receptionist_problems": [
        "receptionist quit",
        "receptionist left",
        "front desk quit",
        "front desk left",
        "need a receptionist",
        "hire a receptionist",
        "hiring a receptionist",
        "can't afford a receptionist",
        "can not afford a receptionist",
        "cannot afford a receptionist",
        "receptionist too expensive",
        "covering the phones myself",
        "answering service",
        "virtual receptionist",
        "phone answering service",
        "call answering service",
        "need someone to answer",
        "office manager quit",
        "front desk coverage",
        "no front desk",
        "solo practice phone",
        "one person office",
    ],

    # =========================================================================
    # BOOKING / SCHEDULING PROBLEMS
    # =========================================================================
    "scheduling_problems": [
        "missed appointment",
        "no-shows",
        "no shows",
        "booking system",
        "appointment booking",
        "scheduling nightmare",
        "scheduling chaos",
        "double booked",
        "overbooking",
        "can't keep up with bookings",
        "too many appointment requests",
        "clients can't book",
    ],

    # =========================================================================
    # CUSTOMER SUPPORT / CHATBOT TRIGGERS
    # =========================================================================
    "customer_support": [
        "need a chatbot",
        "looking for a chatbot",
        "chatbot for my website",
        "chatbot for my business",
        "live chat for website",
        "customer support automation",
        "automate customer service",
        "too many support tickets",
        "support is overwhelming",
        "can't keep up with messages",
        "need help with customer inquiries",
        "FAQ automation",
        "automate responses",
        "24/7 support",
        "24/7 availability",
        "customers expect instant",
        "response time too slow",
    ],

    # =========================================================================
    # LEAD CAPTURE / FOLLOW-UP PROBLEMS
    # =========================================================================
    "lead_problems": [
        "leads going cold",
        "lead goes cold",
        "slow to respond to leads",
        "missed a lead",
        "losing leads",
        "lead follow up",
        "lead follow-up",
        "can't respond fast enough",
        "response time is killing",
        "prospect called but",
        "potential client called",
        "inquiry went unanswered",
    ],

    # =========================================================================
    # SCALING / STAFFING PAIN
    # =========================================================================
    "scaling_problems": [
        "need to scale without hiring",
        "too small to hire",
        "can't afford to hire",
        "can not afford to hire",
        "cannot afford to hire",
        "one man operation",
        "solo operation",
        "only have one truck",
        "growing too fast to handle",
        "overwhelmed with calls",
        "drowning in calls",
        "need help but can't hire",
        "automate my business",
        "business automation",
    ],

    # =========================================================================
    # DIRECT SOLUTION SEARCHES (competitors search these - we do too but
    # they're lower priority since the market is more saturated here)
    # =========================================================================
    "direct_searches": [
        "AI receptionist",
        "AI phone",
        "AI chatbot",
        "AI customer service",
        "AI answering",
        "automated receptionist",
        "virtual assistant for calls",
        "phone bot",
        "call bot",
        "conversational AI",
        "AI for small business",
        "AI for my practice",
        "AI for my office",
    ],
}

# Flatten all keywords into a single list for quick matching
ALL_KEYWORDS = []
for category, keywords in PAIN_KEYWORDS.items():
    ALL_KEYWORDS.extend(keywords)

# =============================================================================
# FORUM TARGETS (scraped with BeautifulSoup/Playwright)
# =============================================================================
FORUMS = {
    "dentaltown": {
        "name": "Dentaltown",
        "base_url": "https://www.dentaltown.com",
        "search_url": "https://www.dentaltown.com/search",
        "type": "dental",
        "scraper": "playwright",  # JS-heavy site
        "enabled": True,
        "description": "250k+ dental professionals, practice management discussions",
    },
    "contractortalk": {
        "name": "ContractorTalk",
        "base_url": "https://www.contractortalk.com",
        "forum_url": "https://www.contractortalk.com/forums/",
        "type": "trades",
        "scraper": "beautifulsoup",
        "enabled": True,
        "description": "Contractor business forum - plumbing, HVAC, electrical",
    },
    "hvactalk": {
        "name": "HVACTalk",
        "base_url": "https://hvac-talk.com",
        "forum_url": "https://hvac-talk.com/vbb/forums/",
        "type": "trades",
        "scraper": "beautifulsoup",
        "enabled": True,
        "description": "HVAC professionals, business operations",
    },
    "lawnsite": {
        "name": "LawnSite",
        "base_url": "https://www.lawnsite.com",
        "forum_url": "https://www.lawnsite.com/forums/",
        "type": "trades",
        "scraper": "beautifulsoup",
        "enabled": True,
        "description": "7M+ posts, lawn/landscaping business forum",
    },
    "insurance_forums": {
        "name": "Insurance Forums",
        "base_url": "https://www.insurance-forums.com",
        "forum_url": "https://www.insurance-forums.com/forum/",
        "type": "insurance",
        "scraper": "beautifulsoup",
        "enabled": True,
        "description": "Independent insurance agent forum, tech section",
    },
}

# =============================================================================
# HACKER NEWS CONFIG
# =============================================================================
HACKERNEWS = {
    "enabled": True,
    "algolia_search_url": "https://hn.algolia.com/api/v1/search_by_date",
    "keywords": [
        "AI receptionist",
        "AI chatbot business",
        "virtual receptionist",
        "missed calls business",
        "chatbot for small business",
        "phone answering service",
        "customer service automation",
        "AI phone system",
    ],
    "max_results": 20,
}

# =============================================================================
# BLUESKY CONFIG
# =============================================================================
BLUESKY = {
    "enabled": True,
    "api_url": "https://public.api.bsky.app",
    "keywords": [
        "need a chatbot",
        "AI receptionist",
        "missed calls",
        "virtual receptionist",
        "chatbot for my business",
        "automate customer service",
        "phone answering AI",
    ],
    "max_results": 25,
}

# =============================================================================
# CLASSIFIER PROMPT (the brain of the system)
# =============================================================================
CLASSIFIER_SYSTEM_PROMPT = """You are a lead qualification assistant for Advance AI Services,
a company that sells AI chatbots and AI phone receptionists to small/medium businesses.

Your job is to classify social media posts and forum messages into three categories:

HOT (score 0.8-1.0): Person is actively looking to BUY or hire someone for:
- AI chatbot / virtual receptionist / phone answering
- They have an immediate problem (missed calls, receptionist quit, overwhelmed)
- They are asking for recommendations or quotes
- They mention a budget or timeline

WARM (score 0.5-0.79): Person has a related problem but hasn't decided on a solution:
- Complaining about missed calls or phone coverage
- Discussing staffing problems (receptionist left, can't afford to hire)
- Asking about automation in general
- Comparing different solutions

COLD (score 0.0-0.49): Not a lead:
- Just discussing AI as a topic (not buying)
- They already have a solution / are selling a solution
- Technical discussion with no buying intent
- Complaints about AI / negative sentiment toward automation
- Student or job seeker (not a business owner)

For each post, return a JSON object with:
- score: float between 0.0 and 1.0
- category: "HOT", "WARM", or "COLD"
- reasoning: brief explanation (1-2 sentences)
- suggested_reply: If HOT or WARM, draft a helpful, non-salesy reply that addresses their specific problem. Be genuine and helpful first. Only mention Advance AI Services casually at the end if it's natural to do so. If COLD, leave empty.

IMPORTANT RULES FOR SUGGESTED REPLIES:
- NEVER be salesy or pushy
- Start by empathizing with their specific problem
- Share a genuine tip or insight related to their situation
- Only mention your service if it naturally fits
- Sound like a helpful human, not a marketing bot
- Keep it under 150 words
"""

# =============================================================================
# TELEGRAM MESSAGE TEMPLATES
# =============================================================================
HOT_ALERT_TEMPLATE = """🔥 *HOT LEAD DETECTED*

*Platform:* {platform}
*Community:* {community}
*Score:* {score}/1.0
*Category:* {category}

*Post:*
{post_text}

*Link:* {post_url}

*Suggested Reply:*
_{suggested_reply}_

*Reasoning:* {reasoning}

⏰ Posted: {time_ago}
"""

WARM_DIGEST_TEMPLATE = """⚡ *WARM LEAD*

*Platform:* {platform}
*Community:* {community}
*Score:* {score}/1.0

*Post:* {post_text_short}
*Link:* {post_url}

*Suggested Reply:*
_{suggested_reply}_
"""

DAILY_DIGEST_TEMPLATE = """📊 *DAILY LEAD DIGEST*

*Today's Summary:*
🔥 HOT leads: {hot_count}
⚡ WARM leads: {warm_count}
❄️ COLD filtered: {cold_count}

*Top Sources:*
{top_sources}

*System Status:* ✅ All scrapers running
*Next scan:* ~30 minutes
"""

# =============================================================================
# DATABASE CONFIG
# =============================================================================
DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "leads.db")

# =============================================================================
# LOGGING
# =============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "monitor.log")
