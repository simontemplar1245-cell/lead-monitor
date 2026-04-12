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
        {"email": "...", "phone": "...", "website": "...",
         "email_source": "website|smtp_verified|mx_guess|post_body|hn_profile|hunter"}
    Empty strings for fields that couldn't be filled.
    Never raises — failures are logged and skipped.
    """
    result = {"email": "", "phone": "", "website": "", "_email_source": ""}
    platform = (lead.get("platform") or "").lower()

    try:
        if platform in ("jobs", "complaints", "craigslist"):
            _enrich_business(lead, result)
        elif platform == "hackernews":
            _enrich_hn_user(lead, result)
            if result["email"]:
                result["_email_source"] = "hn_profile"
        else:
            _enrich_from_post_body(lead, result)
            if result["email"]:
                result["_email_source"] = "post_body"
    except Exception as e:
        logger.warning(f"Enrichment failed for lead {lead.get('id')}: {e}")

    # Always also scan the post body itself as a free bonus pass
    if not (result["email"] and result["phone"]):
        try:
            _enrich_from_post_body(lead, result, allow_overwrite=False)
            if result["email"] and not result["_email_source"]:
                result["_email_source"] = "post_body"
        except Exception:
            pass

    # Map internal source to user-facing confidence label
    source = result.pop("_email_source", "")
    if source in ("website", "hn_profile", "post_body", "hunter"):
        result["email_confidence"] = "verified"
    elif source == "smtp_verified":
        result["email_confidence"] = "verified"
    elif source == "mx_guess":
        result["email_confidence"] = "guessed"
    else:
        result["email_confidence"] = ""

    return result


# =============================================================================
# STRATEGY 1: BUSINESSES (job leads + complaint leads)
# =============================================================================
# Search engines (Google, DDG, Bing) all block server-side scraping in 2026
# with JS-rendering or 202 anti-bot challenges. So we skip search engines
# entirely and use DOMAIN GUESSING + DIRECT WEBSITE SCRAPING:
#
#   1. Turn company name into candidate domains (smithplumbing.com, etc.)
#   2. HEAD-check each domain (~50ms per try, no page load needed)
#   3. Once we find a live domain, scrape /contact, /about for email+phone
#   4. If no email found, check MX records and suggest info@domain.com
#   5. Optional Hunter.io fallback for domains where scraping fails
#
# This is fast (all calls are < 100ms HEAD or < 500ms page fetch), free
# (no API keys), and works from any IP (no anti-bot challenges).
# =============================================================================

def _enrich_business(lead: dict, result: dict):
    """Find a company website via domain guessing, then scrape contact info."""
    company = (lead.get("author") or "").strip()
    if not company:
        return

    # Step 1: guess the company's domain from their name
    domain = _guess_domain(company)
    if not domain:
        logger.debug(f"  no live domain found for '{company}'")
        return

    website = f"https://{domain}"

    # Step 2: validate the domain actually belongs to this company.
    # Fetch homepage and check that the page title / content mentions
    # the company name (or a significant part of it). This prevents
    # "smithplumbing.com" from matching when the company is "Smith Dental".
    homepage_html = _http_get(website)
    if homepage_html and not _domain_matches_company(homepage_html, company):
        logger.debug(f"  domain {domain} doesn't match company '{company}' — skipping")
        return

    result["website"] = website
    logger.info(f"  found website: {website}")

    # Step 3: scrape the homepage + likely contact pages for email/phone
    # Priority: mailto: links > on-page emails > regex-matched emails
    pages_html = {website: homepage_html} if homepage_html else {}
    base = website.rstrip("/")
    for path in ("/contact", "/contact-us", "/about", "/contact.html"):
        page_url = base + path
        if page_url not in pages_html:
            time.sleep(0.3)
            pages_html[page_url] = _http_get(page_url)

    for page_url, html in pages_html.items():
        if result["email"] and result["phone"]:
            break
        if not html:
            continue
        if not result["email"]:
            # Try mailto: links first (most reliable — intentionally published)
            email = _extract_mailto(html, prefer_domain=domain)
            if not email:
                email = _extract_first_email(html, prefer_domain=domain)
            if email:
                result["email"] = email
                result["_email_source"] = "website"
        if not result["phone"]:
            phone = _extract_first_phone(html)
            if phone:
                result["phone"] = phone

    # Step 4: if we found a domain but no email, try common prefixes
    # with SMTP verification before falling back to unverified info@
    if not result["email"] and domain:
        verified = _smtp_verify_common_prefixes(domain)
        if verified:
            result["email"] = verified
            result["_email_source"] = "smtp_verified"
            logger.info(f"  SMTP-verified email: {verified}")
        elif _has_mx_records(domain):
            result["email"] = f"info@{domain}"
            result["_email_source"] = "mx_guess"
            logger.info(f"  MX found, suggesting info@{domain} (unverified)")

    # Step 5: optional Hunter.io fallback
    if not result["email"] and os.getenv("HUNTER_API_KEY"):
        try:
            hunter_email = _hunter_lookup(domain)
            if hunter_email:
                result["email"] = hunter_email
                result["_email_source"] = "hunter"
        except Exception as e:
            logger.debug(f"Hunter.io lookup failed: {e}")


def _guess_domain(company: str) -> Optional[str]:
    """
    Turn a company name into candidate domain names and check which ones
    are live. Returns the first domain that responds, or None.

    e.g. "ABC Heating & Cooling Inc." →
         ["abcheatingandcooling.com", "abcheatingcooling.com",
          "abc-heating-and-cooling.com", "abchvac.com", ...]
    """
    # Normalize: lowercase, strip suffixes, clean punctuation
    name = company.lower()
    # Strip common business suffixes
    for suffix in (" inc", " inc.", " llc", " llp", " ltd", " co.",
                   " corp", " corp.", " company", " group",
                   " services", " service"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    # Replace & with "and", strip non-alphanum
    name = name.replace("&", "and").replace("'", "").replace("'", "")
    name = re.sub(r'[^a-z0-9\s]', '', name).strip()
    words = name.split()

    if not words:
        return None

    candidates = []
    joined = "".join(words)
    hyphenated = "-".join(words)

    # Most likely patterns
    candidates.append(f"{joined}.com")
    candidates.append(f"{hyphenated}.com")
    if len(words) > 2:
        # First + last word (e.g. "abc cooling" from "abc heating and cooling")
        short = words[0] + words[-1]
        candidates.append(f"{short}.com")
    candidates.append(f"{joined}.net")
    candidates.append(f"{joined}.biz")

    for domain in candidates:
        if _domain_is_live(domain):
            return domain

    return None


def _domain_is_live(domain: str) -> bool:
    """Quick HEAD check to see if a domain resolves and serves HTTP."""
    try:
        resp = requests.head(
            f"https://{domain}",
            timeout=4,
            allow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        return resp.status_code < 500
    except Exception:
        # Try HTTP if HTTPS fails
        try:
            resp = requests.head(
                f"http://{domain}",
                timeout=4,
                allow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
            return resp.status_code < 500
        except Exception:
            return False


def _domain_matches_company(html: str, company: str) -> bool:
    """
    Check that a website's content actually mentions the company name.
    Prevents false positives like guessing "smithplumbing.com" when
    the company is "Smith Dental Group".

    We check the <title> tag and the first 5000 chars of visible text.
    Match passes if ANY significant word from the company name (3+ chars,
    not a common suffix) appears in the page.
    """
    if not html or not company:
        return True  # can't verify, assume ok

    # Extract <title> text
    title_m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    page_title = title_m.group(1).lower() if title_m else ""

    # First 5000 chars of text (strip tags cheaply)
    text_chunk = re.sub(r'<[^>]+>', ' ', html[:15000]).lower()[:5000]
    searchable = f"{page_title} {text_chunk}"

    # Normalize company name — extract significant words
    name = company.lower()
    for suffix in (" inc", " inc.", " llc", " llp", " ltd", " co.",
                   " corp", " corp.", " company", " group",
                   " services", " service"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    name = name.replace("&", "and").replace("'", "").replace("\u2019", "")
    name = re.sub(r'[^a-z0-9\s]', '', name).strip()
    words = [w for w in name.split() if len(w) >= 3]

    if not words:
        return True  # too short to verify

    # Match if any significant word appears
    for word in words:
        if word in searchable:
            return True

    return False


def _extract_mailto(html: str, prefer_domain: str = "") -> str:
    """
    Extract email from mailto: links in HTML. These are the most reliable
    emails — the business intentionally published them as clickable links.
    """
    if not html:
        return ""
    # Find all mailto: hrefs
    mailto_re = re.compile(r'href=["\']mailto:([^"\'?]+)', re.IGNORECASE)
    candidates = mailto_re.findall(html)
    if not candidates:
        return ""
    clean = []
    for e in candidates:
        e = e.strip().lower()
        if any(p in e for p in JUNK_EMAIL_PATTERNS):
            continue
        if len(e) > 80 or not EMAIL_RE.match(e):
            continue
        clean.append(e)
    if not clean:
        return ""
    # Prefer same-domain
    if prefer_domain:
        for e in clean:
            if e.endswith("@" + prefer_domain):
                return e
    return clean[0]


def _smtp_verify_common_prefixes(domain: str) -> str:
    """
    Try SMTP RCPT TO check for common business email prefixes.
    Returns the first verified email, or empty string.

    This connects to the mail server, starts a conversation, and asks
    "would you accept mail for info@domain.com?" without actually
    sending anything. Most mail servers give a 250 for valid mailboxes
    and 550 for invalid ones.

    Note: some servers accept all (catch-all) — we detect this by
    testing a random gibberish address first.
    """
    import socket
    import subprocess

    # Get MX server
    mx_host = _get_mx_host(domain)
    if not mx_host:
        return ""

    # Common SMB email prefixes, in order of likelihood
    prefixes = ["info", "contact", "hello", "admin", "office", "support"]

    try:
        sock = socket.create_connection((mx_host, 25), timeout=3)
        sock.settimeout(3)

        def recv():
            return sock.recv(4096).decode(errors="replace")

        def send(msg):
            sock.sendall(f"{msg}\r\n".encode())

        # Read banner
        recv()
        send(f"EHLO leadmonitor.local")
        recv()
        send(f"MAIL FROM:<verify@leadmonitor.local>")
        resp = recv()
        if not resp.startswith("2"):
            sock.close()
            return ""

        # Test a gibberish address first to detect catch-all servers
        send(f"RCPT TO:<xzq8r7m3k2_{domain[:4]}@{domain}>")
        gibberish_resp = recv()
        if gibberish_resp.startswith("2"):
            # Catch-all server — accepts everything, can't verify
            send("QUIT")
            sock.close()
            logger.debug(f"  {domain} is catch-all, can't SMTP-verify")
            return ""

        # Now test real prefixes
        for prefix in prefixes:
            email = f"{prefix}@{domain}"
            send(f"RCPT TO:<{email}>")
            resp = recv()
            if resp.startswith("2"):
                send("QUIT")
                sock.close()
                return email

        send("QUIT")
        sock.close()
    except Exception as e:
        logger.debug(f"  SMTP verify failed for {domain}: {e}")

    return ""


def _get_mx_host(domain: str) -> str:
    """Get the primary MX host for a domain."""
    import subprocess
    try:
        result = subprocess.run(
            ["dig", "+short", "MX", domain],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split("\n")
        if not lines or not lines[0]:
            return ""
        # MX records look like: "10 mail.example.com."
        # Pick lowest priority (first after sorting)
        mx_entries = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2:
                priority = int(parts[0])
                host = parts[1].rstrip(".")
                mx_entries.append((priority, host))
        if mx_entries:
            mx_entries.sort()
            return mx_entries[0][1]
    except Exception:
        pass
    return ""


def _has_mx_records(domain: str) -> bool:
    """Check if a domain has MX records (= accepts email)."""
    import subprocess
    try:
        result = subprocess.run(
            ["dig", "+short", "MX", domain],
            capture_output=True, text=True, timeout=5
        )
        return bool(result.stdout.strip())
    except Exception:
        # dig not available — try nslookup as fallback
        try:
            result = subprocess.run(
                ["nslookup", "-type=MX", domain],
                capture_output=True, text=True, timeout=5
            )
            return "mail exchanger" in result.stdout.lower()
        except Exception:
            return False


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
                    email_confidence=result.get("email_confidence", ""),
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
