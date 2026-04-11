"""
Complaint Scraper
=================
Mines public review sites for small businesses that customers are
complaining about for reachability / missed-calls / phone problems.
These are the HIGHEST intent leads we can possibly find: a review that
says "called six times, nobody ever answered" is a business owner who
is DEMONSTRABLY losing revenue to exactly the problem our AI receptionist
solves.

Strategy (all free, no paid APIs):
  1. Query DuckDuckGo HTML for targeted complaint phrases scoped to a
     specific review site: `site:yelp.com "never answered the phone" dentist`
  2. Fetch each result page.
  3. Extract business name, review snippet, and URL.
  4. Emit as lead with platform="complaints", community="<site>".

Target sites:
  - Yelp (huge review volume, scrapeable HTML)
  - BBB (complaints section is goldmine for phone pain)
  - Trustpilot (businesses review themselves, strong pain signals)
  - Google Maps reviews show up in DDG results too

We do NOT use the Google Places API (paid) or headless browsers — just
plain HTTP so the scraper is fast and works in CI without extra deps.
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import Generator
from urllib.parse import quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from config import COMPLAINTS

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class ComplaintScraper:
    """Mines review sites for business phone-pain complaints."""

    def __init__(self):
        self.enabled = COMPLAINTS.get("enabled", True)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.max_results_per_query = COMPLAINTS.get("max_results_per_query", 8)
        self.request_delay = COMPLAINTS.get("request_delay_seconds", 1.5)

    # =========================================================================
    # ENTRY POINT
    # =========================================================================

    def scan_all(self) -> Generator[dict, None, None]:
        """Run every configured (site, phrase, vertical) combo."""
        if not self.enabled:
            return

        sites = COMPLAINTS.get("sites", [])
        phrases = COMPLAINTS.get("complaint_phrases", [])
        verticals = COMPLAINTS.get("verticals", [""])

        seen_urls = set()
        ddg_total_hits = 0
        emitted = 0
        rejected_for_snippet = 0

        for site in sites:
            site_domain = site["domain"]
            site_name = site["name"]
            logger.info(f"Complaint scan: {site_name}")

            for phrase in phrases:
                for vertical in verticals:
                    query_parts = [f'site:{site_domain}', f'"{phrase}"']
                    if vertical:
                        query_parts.append(vertical)
                    query = " ".join(query_parts)

                    try:
                        hits = self._search_ddg(query)
                        ddg_total_hits += len(hits)
                        for result in hits:
                            if result["url"] in seen_urls:
                                continue
                            seen_urls.add(result["url"])

                            lead = self._build_lead(result, site_name, phrase)
                            if lead:
                                emitted += 1
                                yield lead
                            else:
                                rejected_for_snippet += 1

                        time.sleep(self.request_delay)
                    except Exception as e:
                        logger.warning(
                            f"Complaint search failed for '{query}': {e}"
                        )

        logger.info(
            f"Complaint scan stats: ddg_hits={ddg_total_hits} "
            f"emitted={emitted} rejected_for_non_phone_context={rejected_for_snippet}"
        )
        if ddg_total_hits == 0:
            logger.warning(
                "Complaint scraper got ZERO DDG hits — DuckDuckGo may be "
                "rate-limiting this IP. This is usually transient; if it "
                "persists across multiple scans, consider switching to a "
                "different search backend."
            )

    # =========================================================================
    # DUCKDUCKGO SEARCH
    # =========================================================================

    def _search_ddg(self, query: str) -> list:
        """
        Use the DDG HTML endpoint (no API key) and return up to N result
        dicts: {'url': ..., 'title': ..., 'snippet': ...}
        """
        try:
            resp = self.session.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers={**HEADERS, "Referer": "https://duckduckgo.com/"},
                timeout=15,
            )
            if resp.status_code != 200:
                return []
            html = resp.text
        except requests.RequestException as e:
            logger.debug(f"DDG query failed: {e}")
            return []

        results = []
        soup = BeautifulSoup(html, "lxml")
        # DDG HTML layout: <div class="result"> containing <a class="result__a"> + <a class="result__snippet">
        for div in soup.select("div.result")[: self.max_results_per_query]:
            a = div.select_one("a.result__a")
            if not a:
                continue
            href = a.get("href", "")
            # DDG wraps outgoing links as /l/?uddg=<encoded>
            if "uddg=" in href:
                m = re.search(r"uddg=([^&]+)", href)
                if m:
                    href = unquote(m.group(1))
            if not href.startswith("http"):
                continue
            title = a.get_text(" ", strip=True)

            snippet_el = div.select_one(".result__snippet")
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""

            results.append({"url": href, "title": title, "snippet": snippet})
        return results

    # =========================================================================
    # LEAD BUILDER
    # =========================================================================

    # Tokens that MUST appear in the snippet for a result to be a real
    # phone/reachability complaint (vs. a random "bad food" 1-star review
    # that happens to share wording with our search phrase). This is the
    # hard filter that prevents false positives from the complaint scraper.
    PHONE_PAIN_TOKENS = (
        "phone", "call", "called", "calling",
        "voicemail", "voice mail", "voice-mail",
        "answer", "answered", "pick up", "picked up",
        "reach", "reached", "reaching", "unreachable",
        "contact", "get through", "got through",
        "respond", "respond to", "return my call",
        "ring", "rang", "ringing", "hung up",
    )

    def _build_lead(self, result: dict, site_name: str,
                    complaint_phrase: str) -> dict:
        """
        Turn a search result into a lead. We trust DDG's snippet for the
        review text itself — it typically already contains the complaint.
        Fetching the full page is optional and only done if we want more
        detail later (it's slower and many sites block scrapers).
        """
        url = result["url"]
        title = (result.get("title") or "").strip()
        snippet = (result.get("snippet") or "").strip()

        if not snippet:
            # Skip empty results — no signal to classify
            return None

        # HARD FILTER: the snippet OR title must actually mention phone-
        # related pain words. This keeps out 1-star reviews that are
        # really about food, pricing, rudeness, etc. even if they happen
        # to contain our search phrase somewhere. Without this, generic
        # "the business is bad" complaints would slip through.
        combined = f"{title} {snippet}".lower()
        if not any(token in combined for token in self.PHONE_PAIN_TOKENS):
            logger.debug(
                f"Complaint lead rejected (no phone-pain token): {title[:60]}"
            )
            return None

        # Business name extraction heuristic: Yelp/BBB titles look like
        # "Acme Plumbing - Reviews - 123 Main St - Yelp" or similar.
        # Strip trailing site name and location crumbs.
        business_name = self._extract_business_name(title, site_name)

        post_id = (
            f"complaint_{hashlib.md5(url.encode()).hexdigest()[:16]}"
        )

        return {
            "post_id": post_id,
            "platform": "complaints",
            "community": site_name,
            "author": business_name,
            "title": title[:200],
            "body": snippet[:500],
            "url": url,
            "post_created_at": datetime.now(timezone.utc).isoformat(),
            # full_text is what the classifier matches keywords against.
            # Prepend the complaint phrase so the matcher can't miss it.
            "full_text": f"{complaint_phrase}. {title}. {snippet}",
        }

    def _extract_business_name(self, title: str, site_name: str) -> str:
        """
        Heuristic: most review-site titles put the business name first,
        separated by " - " or " | " from reviews/location metadata.
        Fall back to the full title if the split doesn't look right.
        """
        if not title:
            return ""
        for sep in (" - ", " | ", " – ", " — "):
            if sep in title:
                first = title.split(sep)[0].strip()
                if 2 <= len(first) <= 100:
                    return first
        # Strip trailing site name
        for suffix in (f" {site_name}", f" on {site_name}"):
            if title.lower().endswith(suffix.lower()):
                return title[: -len(suffix)].strip()
        return title[:100]
