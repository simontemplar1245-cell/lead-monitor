"""
Contact Enrichment
==================
Tries to find an email / phone / website for each HOT/WARM lead so the
dashboard can offer real outreach actions (mailto:, tel:) instead of
just opening searches.

Strategies (all free, no paid APIs required):

1. JOB leads (Indeed/LinkedIn): the post itself has the company name only.
   - Search DuckDuckGo HTML for "<company name> contact"
   - Visit the top result + a /contact page if found
   - Regex emails and phone numbers out of the HTML
   - First sensible match wins

2. HACKER NEWS leads: HN profiles often list an email in the 'about' field.
   - Hit https://hacker-news.firebaseio.com/v0/user/<username>.json
   - Parse 'about' for email + URL

3. REDDIT / FORUM / BLUESKY leads: extract any email/URL the user already
   pasted in their post body.

If HUNTER_API_KEY is set we also try Hunter.io's domain-search endpoint
(25 free lookups/month). Skipped silently if no key.

Designed to FAIL OPEN: every step is wrapped in try/except, network errors
just leave the lead unenriched. Never blocks the scan.
"""

import logging
import os
import re
import time
from typing import Optional
from urllib.parse import quote_plus, urlparse

import requests

logger = logging.getLogger(__name__)

# How long to wait for any single HTTP request
HTTP_TIMEOUT = 8

# How long to wait between requests to be polite to other people's servers
REQUEST_DELAY = 1.0

# Realistic browser UA — DDG and many sites block obvious bot UAs
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)

# Email regex — keep simple, we filter junk afterwards
EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# US-style phone numbers, fairly forgiving
PHONE_RE = re.compile(
    r"(?:\+?1[\s.\-]?)?\(?(\d{3})\)?[\s.\-]?(\d{3})[\s.\-]?(\d{4})"
)

URL_RE = re.compile(r"https?://[^\s<>\"']+")

# Junk-email patterns we never want to surface as the contact
JUNK_EMAIL_PATTERNS = (
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "example.com", "example.org", "yourdomain", "test@",
    "wixpress.com", "sentry.io", "wordpress.com",
    ".png", ".jpg", ".gif", ".webp", ".svg",
    "u003e", "u003c",  # escaped HTML in JSON
)

# Domains we never want to follow as a "company website" (these are
# directories / job boards, not real businesses)
BLOCKED_DOMAINS = {
    "indeed.com", "linkedin.com", "glassdoor.com", "ziprecruiter.com",
    "monster.com", "simplyhired.com", "google.com", "facebook.com",
    "twitter.com", "x.com", "instagram.com", "wikipedia.org",
    "yelp.com", "bbb.org", "youtube.com", "reddit.com",
    "duckduckgo.com",
}


# =============================================================================
# PUBLIC ENTRYPOINT
# =============================================================================

def enrich_lead(lead: dict) -> dict:
    """
    Try to find email / phone / website for one lead.
    Returns dict with whatever was found:
        {"email": "...", "phone": "...", "website": "..."}
    Empty strings for fields that couldn't be filled.
    Never raises — failures are logged and skipped.
    """
    result = {"email": "", "phone": "", "website": ""}
    platform = (lead.get("platform") or "").lower()

    try:
        if platform == "jobs":
            _enrich_business(lead, result)
        elif platform == "hackernews":
            _enrich_hn_user(lead, result)
        else:
            _enrich_from_post_body(lead, result)
    except Exception as e:
        logger.warning(f"Enrichment failed for lead {lead.get('id')}: {e}")

    # Always also scan the post body itself as a free bonus pass
    if not (result["email"] and result["phone"]):
        try:
            _enrich_from_post_body(lead, result, allow_overwrite=False)
        except Exception:
            pass

    return result


# =============================================================================
# STRATEGY 1: BUSINESSES (job leads)
# =============================================================================

def _enrich_business(lead: dict, result: dict):
    """Find a company website + scrape it for contact info."""
    company = (lead.get("author") or "").strip()
    if not company:
        return

    # Step 1: find the company website via DDG
    website = _ddg_top_result(f"{company} contact")
    if not website:
        # Try a softer query
        website = _ddg_top_result(f"{company} official site")
    if not website:
        return

    result["website"] = website
    logger.info(f"  found website: {website}")

    # Step 2: scrape the homepage + likely contact pages
    pages_to_try = [website]
    base = website.rstrip("/")
    for path in ("/contact", "/contact-us", "/about", "/contact.html"):
        pages_to_try.append(base + path)

    for url in pages_to_try:
        if result["email"] and result["phone"]:
            break
        time.sleep(REQUEST_DELAY)
        html = _http_get(url)
        if not html:
            continue
        if not result["email"]:
            email = _extract_first_email(html, prefer_domain=_domain_of(website))
            if email:
                result["email"] = email
        if not result["phone"]:
            phone = _extract_first_phone(html)
            if phone:
                result["phone"] = phone

    # Step 3: optional Hunter.io fallback if we still have nothing
    if not result["email"] and os.getenv("HUNTER_API_KEY"):
        try:
            hunter_email = _hunter_lookup(_domain_of(website))
            if hunter_email:
                result["email"] = hunter_email
        except Exception as e:
            logger.debug(f"Hunter.io lookup failed: {e}")


# =============================================================================
# STRATEGY 2: HACKER NEWS USERS
# =============================================================================

def _enrich_hn_user(lead: dict, result: dict):
    """HN profiles often have an email in the 'about' field."""
    username = (lead.get("author") or "").strip()
    if not username:
        return
    try:
        resp = requests.get(
            f"https://hacker-news.firebaseio.com/v0/user/{username}.json",
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code != 200:
            return
        data = resp.json() or {}
        about = data.get("about", "") or ""
        if not about:
            return
        email = _extract_first_email(about)
        if email:
            result["email"] = email
        url_match = URL_RE.search(about)
        if url_match and not result["website"]:
            result["website"] = url_match.group(0).rstrip(".,)")
    except Exception as e:
        logger.debug(f"HN user lookup failed: {e}")


# =============================================================================
# STRATEGY 3: POST BODY (Reddit / forums / Bluesky)
# =============================================================================

def _enrich_from_post_body(lead: dict, result: dict, allow_overwrite: bool = True):
    """Some users paste their email or website right in the post."""
    body = (lead.get("body") or "") + " " + (lead.get("title") or "")
    if not body.strip():
        return
    if (allow_overwrite or not result["email"]):
        email = _extract_first_email(body)
        if email:
            result["email"] = email
    if (allow_overwrite or not result["phone"]):
        phone = _extract_first_phone(body)
        if phone:
            result["phone"] = phone
    if (allow_overwrite or not result["website"]):
        m = URL_RE.search(body)
        if m:
            url = m.group(0).rstrip(".,)")
            if _domain_of(url) not in BLOCKED_DOMAINS:
                result["website"] = url


# =============================================================================
# DUCKDUCKGO HTML SEARCH (no API key needed)
# =============================================================================

def _ddg_top_result(query: str) -> Optional[str]:
    """
    Use the DDG HTML endpoint to find the top organic result for a query.
    Returns the first non-blocked URL, or None.
    """
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://duckduckgo.com/",
            },
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        html = resp.text
        # Result links look like: <a class="result__a" href="https://...">
        for m in re.finditer(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', html
        ):
            url = m.group(1)
            # DDG redirects through /l/?uddg=<encoded>; unwrap if needed
            if "uddg=" in url:
                from urllib.parse import unquote
                m2 = re.search(r"uddg=([^&]+)", url)
                if m2:
                    url = unquote(m2.group(1))
            domain = _domain_of(url)
            if domain and domain not in BLOCKED_DOMAINS:
                return url
        return None
    except Exception as e:
        logger.debug(f"DDG search failed for '{query}': {e}")
        return None


# =============================================================================
# HTTP HELPERS
# =============================================================================

def _http_get(url: str) -> str:
    """Fetch a URL with a real-browser UA. Returns '' on any error."""
    try:
        resp = requests.get(
            url,
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return ""
        # Avoid loading huge binaries
        ct = resp.headers.get("Content-Type", "")
        if "text/html" not in ct and "application/xhtml" not in ct:
            return ""
        return resp.text[:300_000]  # cap at 300KB
    except Exception:
        return ""


# =============================================================================
# EXTRACTION
# =============================================================================

def _extract_first_email(text: str, prefer_domain: str = "") -> str:
    """Find the first sensible email in text. Prefer same-domain matches."""
    if not text:
        return ""
    candidates = EMAIL_RE.findall(text)
    if not candidates:
        return ""
    clean = []
    for e in candidates:
        e = e.strip().lower()
        if any(p in e for p in JUNK_EMAIL_PATTERNS):
            continue
        # Sanity: emails shouldn't be more than ~80 chars
        if len(e) > 80:
            continue
        clean.append(e)
    if not clean:
        return ""
    if prefer_domain:
        for e in clean:
            if e.endswith("@" + prefer_domain):
                return e
    return clean[0]


def _extract_first_phone(text: str) -> str:
    """Find the first sensible phone number in text."""
    if not text:
        return ""
    for m in PHONE_RE.finditer(text):
        area, mid, last = m.groups()
        # Reject obvious garbage like 000-000-0000
        if area in ("000", "111") or mid in ("000", "111"):
            continue
        return f"({area}) {mid}-{last}"
    return ""


def _domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


# =============================================================================
# OPTIONAL HUNTER.IO FALLBACK
# =============================================================================

def _hunter_lookup(domain: str) -> str:
    """Hunter.io domain search — only runs if HUNTER_API_KEY is set."""
    api_key = os.getenv("HUNTER_API_KEY", "")
    if not api_key or not domain:
        return ""
    try:
        resp = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": api_key, "limit": 1},
            timeout=HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            return ""
        data = resp.json() or {}
        emails = (data.get("data") or {}).get("emails") or []
        if emails:
            return emails[0].get("value", "")
    except Exception as e:
        logger.debug(f"Hunter.io error: {e}")
    return ""


# =============================================================================
# BATCH RUNNER
# =============================================================================

def enrich_pending_leads(db, limit: int = 30):
    """
    Top-level: pull HOT/WARM leads that haven't been enriched yet,
    enrich each one, write contact info back to the DB.
    Bounded by `limit` to avoid blowing up scan time.
    """
    leads = db.get_leads_to_enrich(limit=limit)
    if not leads:
        logger.info("Enrichment: no pending leads")
        return {"attempted": 0, "found_email": 0, "found_phone": 0}

    logger.info(f"Enrichment: processing {len(leads)} leads")
    stats = {"attempted": 0, "found_email": 0, "found_phone": 0}

    for lead in leads:
        stats["attempted"] += 1
        try:
            result = enrich_lead(lead)
            if result["email"] or result["phone"] or result["website"]:
                db.update_contact_info(
                    lead["id"],
                    email=result["email"],
                    phone=result["phone"],
                    website=result["website"],
                )
                if result["email"]:
                    stats["found_email"] += 1
                if result["phone"]:
                    stats["found_phone"] += 1
                logger.info(
                    f"  enriched lead {lead['id']} ({lead.get('author', '?')[:30]}): "
                    f"email={'Y' if result['email'] else 'N'} "
                    f"phone={'Y' if result['phone'] else 'N'}"
                )
            else:
                # Mark as enriched anyway so we don't retry forever
                db.update_contact_info(lead["id"])
        except Exception as e:
            logger.warning(f"  enrichment error on lead {lead.get('id')}: {e}")

    logger.info(
        f"Enrichment complete: {stats['found_email']} emails, "
        f"{stats['found_phone']} phones from {stats['attempted']} leads"
    )
    return stats
