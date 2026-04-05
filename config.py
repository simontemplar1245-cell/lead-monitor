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

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh")

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
        # Trades / Blue-collar (PERFECT for AI receptionist - "can't answer on the job")
        "sweatystartup",       # ~118k - blue collar entrepreneurs, miss calls on jobs
        "pressurewashing",     # ~53k - owner-operators, phone/dispatch pain
        "WindowCleaning",      # ~9k - "on a ladder can't answer" phrasing
        "CarpetCleaning",      # ~9k - high owner density, service admin burden
        "cleaningbusiness",    # ~5k - niche but almost all owners
        "PoolPros",            # ~4k - route work + scheduling = missed calls
        "lawncare",            # ~680k - mix but many biz owners, seasonal call spikes
        "Roofing",             # ~152k - contractors, strict anti-spam but good for monitoring
        "Locksmith",           # ~35k - mobile trade, miss calls on jobs

        # Dental
        "Dentistry",           # ~130k - practice owners, front desk problems

        # Legal
        "Lawyertalk",          # ~65k - solo/small firm lawyers, intake problems
        "LawFirm",            # ~99k - explicitly for practice operations

        # Insurance
        "InsuranceAgent",      # ~10k - tiny but perfectly targeted

        # Real Estate
        "realtors",            # ~92k - agents, lead response anxiety
        "RealEstateTechnology", # ~49k - tools/process discussions, chatbot/lead response

        # Property Management (NEW from research - strong "maintenance calls" pain)
        "PropertyManagement",  # ~43k - "maintenance calls", "tenant comms", "after-hours"

        # Mortgage/Lending (NEW from research - phone-heavy pipeline)
        "loanoriginators",     # ~30k - professionals discussing pipelines, leads, operations

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
        "Entrepreneur",        # ~5.1M - very large, noise but high volume

        # E-commerce (chatbot buyers)
        "ecommerce",           # ~200k - store owners needing chat support
        "shopify",             # ~200k - store owners

        # Accounting (seasonal pain)
        "Accounting",          # ~468k - tax season call overload

        # Veterinary (NEW from research - staffing/burnout/ops discussions)
        "veterinaryprofession", # ~29k - pros discuss staffing, operational bottlenecks
        "VetTech",             # ~30k - some practice management discussion

        # Medical/Health practices
        "optometry",           # ~25k - practice workflow, front desk themes
        "physicaltherapy",     # ~94k - clinic owners, intake/front desk pain
        "Chiropractic",        # ~89k - practice management, front desk topics

        # Commercial Real Estate (NEW from research - leasing calls, ops)
        "CommercialRealEstate", # ~123k - investors/operators, leasing/vendor discussions

        # Pest Control (NEW from research - industry language mining)
        "pestcontrol",         # ~94k - consumer-heavy but industry discussions exist

        # HIRING-SIDE SUBREDDITS (proven: businesses post [HIRING]
        # chatbot / AI / virtual assistant requests here daily)
        "forhire",             # ~710k - [HIRING] tag for client-side posts
        "hireaprogrammer",     # ~48k - explicitly for hiring devs
        "jobbit",              # ~23k - remote gigs, client-side heavy
        "DoneDirtCheap",       # ~75k - quick gigs, some chatbot requests
        "HireanIllustrator",   # ~11k - proof this subreddit pattern works
        "slavelabour",         # ~365k - cheap gigs (use carefully)
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

        # NEW - more buyer-dense niches from 2026 research
        "MedicalAesthetics",   # med spa owners, appointment-heavy
        "Esthetics",           # estheticians - solo owners
        "Barber",              # barbers, solo/small shop owners
        "MassageTherapists",   # massage therapists, booking-heavy
        "tax",                 # tax preparers, seasonal phone overload
        "bookkeeping",         # bookkeepers dealing with client inquiries
        "AskPhotography",      # photographers, inquiry management
        "Weddingsunder10k",    # wedding vendors, high-inquiry
        "personaltraining",    # PTs / gym owners with scheduling
        "therapists",          # small practice therapists
        "privatepractice",     # healthcare private practices
        "DogGrooming",         # groomers, appointment-based
        "dogtraining",         # trainers, inquiry-heavy
        "AskContractors",      # Q&A for contractors / owners
        "homeimprovement",     # mix of DIY + pro contractors
        "GeneralContractor",   # owner-operators
        "handyman",            # solo operators, miss calls on jobs
        "Welding",             # mobile welders, miss calls on jobs
        "TowTruck",            # dispatchers, 24/7 call requirements
        "junkremoval",         # route-based, estimate calls
        "Moving",              # movers community (replaces private r/movers)
        "selfstorage",         # facility owners, inquiry calls
        "notary",              # mobile notaries, appointment-based
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
        "phone ringing off the hook",
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
        "after-hours call management",
        "nights and weekends",
        "emergency calls after hours",
        "emergency maintenance line",
        "weekend calls",
        "lost the job because",
        "customer went to competitor",
        "customers going to competitors",
        "lost a customer because",
        "losing customers because",
        "didn't answer in time",
        # Field-service specific (from research - operators in the field)
        "can't get back to",
        "missed a booking",
        "lost the booking",
        "call back backlog",
        "in the field can't answer",
        "on a ladder",
        "hands full",
        "driving between jobs",
        "call overflow",
        "too many inbound calls",
    ],

    # =========================================================================
    # RECEPTIONIST / FRONT DESK PROBLEMS
    # =========================================================================
    "receptionist_problems": [
        "receptionist quit",
        "receptionist left",
        "front desk quit",
        "front desk left",
        "front office",
        "need a receptionist",
        "hire a receptionist",
        "hiring a receptionist",
        "can't afford a receptionist",
        "can not afford a receptionist",
        "cannot afford a receptionist",
        "can't hire front desk",
        "receptionist too expensive",
        "covering the phones myself",
        "answering service",
        "virtual receptionist",
        "phone answering service",
        "call answering service",
        "need someone to answer",
        "office manager quit",
        "front desk coverage",
        "front desk overload",
        "no front desk",
        "solo practice phone",
        "one person office",
        # Intake-specific (from research - legal, medical, vet)
        "intake",
        "new patient intake",
        "client intake",
        "lead intake",
        "intake coordinator",
        "intake calls",
        "call triage",
        "phone triage",
    ],

    # =========================================================================
    # BOOKING / SCHEDULING PROBLEMS
    # =========================================================================
    "scheduling_problems": [
        "missed appointment",
        "no-shows",
        "no shows",
        "no-show rate",
        "late cancellations",
        "booking system",
        "appointment booking",
        "appointment reminders",
        "scheduling nightmare",
        "scheduling chaos",
        "schedule is slammed",
        "calendar is a mess",
        "double booked",
        "double-booked",
        "overbooked",
        "overbooking",
        "can't keep up with bookings",
        "too many appointment requests",
        "clients can't book",
        "reschedule backlog",
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
    # =========================================================================
    # INDUSTRY-SPECIFIC OPERATIONS (from deep research - operators use
    # role/workflow terms, not "AI" terms. These are high-signal when
    # they co-occur with missed calls/overwhelmed phrases)
    # =========================================================================
    "industry_specific": [
        # Dental/clinic ops
        "insurance verification",
        "benefits verification",
        "new patient calls",
        "patient recall",
        "reactivation",
        # Veterinary ops
        "client service representative",
        "curbside",
        "triage calls",
        # Auto repair shop ops
        "service advisor",
        "service writer",
        "estimate approval",
        "authorise the estimate",
        "authorize the estimate",
        "repair order",
        "status update calls",
        "vehicle ready call",
        # Property management ops
        "maintenance requests",
        "work order",
        "leasing calls",
        "rental inquiries",
        "tenant portal",
        "after-hours maintenance",
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

    # =========================================================================
    # HIRING-INTENT SIGNALS (from research: a business actively trying to
    # hire a receptionist / front desk person is the STRONGEST possible
    # buying signal for AI receptionist services - they've already decided
    # they need one, they just don't know an AI can do the job for 10% of
    # the cost. These phrases appear in Reddit posts, job boards, etc.)
    # =========================================================================
    "hiring_signals": [
        "hiring a receptionist",
        "hiring receptionist",
        "looking to hire receptionist",
        "looking for a receptionist",
        "need to hire front desk",
        "hiring front desk",
        "hiring front office",
        "posting a job for",
        "job posting receptionist",
        "job ad for receptionist",
        "struggling to hire receptionist",
        "can't find a good receptionist",
        "cant find a receptionist",
        "no luck hiring",
        "receptionist candidates",
        "front desk candidates",
        "receptionist turnover",
        "high turnover front desk",
        "back-to-back receptionists",
        "receptionist salary",
        "receptionist wage",
        "what to pay receptionist",
        "virtual assistant hire",
        "hiring virtual assistant",
        "outsource reception",
        "outsource answering",
        "answering service cost",
        "how much does a receptionist cost",
        "replace receptionist",
        "replacing my receptionist",
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
    # NEW FORUMS FROM RESEARCH
    "optiboard": {
        "name": "OptiBoard",
        "base_url": "https://www.optiboard.com",
        "forum_url": "https://www.optiboard.com/forums",
        "type": "optometry",
        "scraper": "beautifulsoup",
        "enabled": True,
        "description": "Optometry professionals, practice management areas",
    },
    "autoshopowner": {
        "name": "AutoShopOwner",
        "base_url": "https://www.autoshopowner.com",
        "forum_url": "https://www.autoshopowner.com/forums/",
        "type": "auto_repair",
        "scraper": "beautifulsoup",
        "enabled": True,
        "description": "Auto repair shop management - staffing, customer comms, operations",
    },
    "physicaltherapist": {
        "name": "PhysicalTherapist.com",
        "base_url": "https://www.physicaltherapist.com",
        "forum_url": "https://www.physicaltherapist.com",
        "type": "healthcare",
        "scraper": "beautifulsoup",
        "enabled": True,
        "description": "Open PT forum - clinic owners discuss intake, scheduling, staffing",
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
    # NOTE: public.api.bsky.app started returning 403 from some IP ranges
    # in early 2026 - use the main api.bsky.app endpoint instead.
    # Unauthenticated search still works here.
    "api_url": "https://api.bsky.app",
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
# JOBS CONFIG (JobSpy - scrapes Indeed / ZipRecruiter / LinkedIn / Glassdoor)
# =============================================================================
# STRATEGY: A business posting a "receptionist" or "front desk" job listing is
# the single STRONGEST buying signal we can find on the internet. They've
# already decided they need reception coverage - they just don't know yet
# that an AI can do it for 10% of the cost. These are the highest-intent
# "leads" on the planet. Every posting we find = a business we can cold-pitch.
#
# JobSpy is free, open source, no API key. It scrapes multiple boards in one
# call. Each scan pulls fresh postings (last 24h) so we don't re-contact.
JOBS = {
    "enabled": True,
    # Which boards to pull from (no auth needed for any of these)
    # NOTE: Glassdoor removed - its API returns 400 for generic location
    # strings like "United States" and its location parser is broken.
    # NOTE: ZipRecruiter removed - Cloudflare WAF now returns 403 "forbidden
    # cf-waf" on every request from GitHub Actions IPs. Dead weight.
    # LinkedIn kept but tends to rate-limit aggressively so it adds little.
    # Indeed is the workhorse - free, reliable, huge coverage, no auth.
    "sites": ["indeed", "linkedin"],

    # STRATEGY UPDATE: An AI receptionist cannot replace a physical front
    # desk worker (who greets patients, hands over paperwork, etc.). It CAN
    # replace the purely phone/virtual side of reception. So we prioritise
    # search terms for ROLES THAT ARE 100% PHONE / REMOTE / VIRTUAL, and
    # we pass is_remote=True to JobSpy plus strict post-filtering to
    # guarantee only AI-replaceable jobs survive into the lead list.
    "search_terms": [
        # Tier A - pure phone/virtual roles (highest intent, 100% replaceable)
        "virtual receptionist",
        "remote receptionist",
        "telephone receptionist",
        "phone receptionist",
        "call center representative remote",
        "remote customer service",
        "inbound call agent remote",
        # Tier B - intake/scheduling roles (usually remote-friendly)
        "appointment scheduler remote",
        "remote intake coordinator",
        "virtual assistant scheduler",
        "remote patient access",
        # Tier C - broader catch (requires remote flag to survive)
        "remote receptionist part time",
        "work from home receptionist",
        # Tier D - CHATBOT-BUILD signals: businesses hiring someone to
        # build a chatbot = businesses that want to BUY a chatbot solution.
        # Same buyer intent from the opposite angle. Proven - these hit.
        "chatbot developer",
        "conversational AI developer",
        "AI chatbot integration",
        "voice AI developer",
        "build chatbot contract",
    ],
    # Geographic focus - US/Canada/UK (English markets where we can sell)
    "locations": [
        "United States",
        "Canada",
        "United Kingdom",
    ],
    # Recency - Indeed doesn't always remove filled jobs, so fresher =
    # higher chance the role is still open. 168h (7 days) is the sweet
    # spot: recent enough most are still open, long enough to catch
    # jobs posted over a weekend before Monday processing. Well within
    # the hard cap of 720h (30 days) for the "no older than a month" rule.
    "hours_old": 168,  # 7 days
    # Results per search term per location (keep small - avoid rate limits)
    "results_per_search": 15,
    # STRICT REMOTE FILTER: only keep jobs where JobSpy confirmed remote=True
    # OR the title explicitly contains remote/virtual/phone language.
    "strict_remote_only": True,
    # Titles we IGNORE (noise we don't want in the leads list)
    "exclude_titles": [
        "director",
        "manager",
        "supervisor",
        "lead receptionist",
        "head of",
        "chief",
        "senior",   # enterprise roles - have procurement, can't cold-pitch
        "lead ",
    ],
    # Companies to EXCLUDE - these ARE the competitors we're trying to
    # displace. Hiring by them is not a lead, it's a red flag.
    "exclude_companies": [
        "always on call",
        "answerconnect",
        "ruby receptionists",
        "posh virtual receptionists",
        "moneypenny",
        "specialty answering service",
        "answer 1",
        "abby connect",
        "smith.ai",
        "nexa",
        "davinci virtual",
        "call ruby",
        "conversational receptionists",
        "map communications",
        "answering service care",
    ],
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
# NTFY.SH MESSAGE TEMPLATES (plain text - ntfy doesn't use markdown)
# =============================================================================
# The notification IS the entire lead brief - user reads it, decides, taps link.
# Every template includes: who (company/author), what (title/summary),
# when (posted time), where (link), why (reasoning), and next step (suggested reply).

HOT_ALERT_TEMPLATE = """🔥 HOT LEAD

WHO: {company}
WHAT: {title}
WHERE: {platform} / {community}
WHEN: Posted {time_ago}
SCORE: {score}/1.0

SUMMARY:
{post_text}

WHY THIS IS A LEAD:
{reasoning}

SUGGESTED REPLY:
{suggested_reply}

🔗 OPEN: {post_url}
"""

WARM_DIGEST_TEMPLATE = """⚡ WARM LEAD

WHO: {company}
WHAT: {title}
WHERE: {platform} / {community}
WHEN: Posted {time_ago}
SCORE: {score}/1.0

SUMMARY:
{post_text_short}

WHY: {reasoning}

SUGGESTED REPLY:
{suggested_reply}

🔗 OPEN: {post_url}
"""

# Job postings get a specialized template since "author" = the hiring company,
# "title" = the role, and there's no "reply" - you cold-pitch the company direct.
JOB_ALERT_TEMPLATE = """💼 HIRING SIGNAL ({category})

COMPANY: {company}
ROLE: {title}
SOURCE: {platform} / {community}
POSTED: {time_ago}

ROLE SUMMARY:
{post_text}

WHY THIS IS A LEAD:
{company} is actively trying to hire someone to do phone/reception work.
That's the exact job your AI receptionist does - for ~10% of the salary cost.
They've already decided they need the function. Pitch them now before they
hire a human.

COLD-PITCH ANGLE:
{suggested_reply}

🔗 JOB POSTING: {post_url}
"""

DAILY_DIGEST_TEMPLATE = """DAILY LEAD DIGEST

Today's Summary:
HOT leads: {hot_count}
WARM leads: {warm_count}
COLD filtered: {cold_count}

Top Sources:
{top_sources}

System Status: All scrapers running
Next scan: ~30 minutes
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
