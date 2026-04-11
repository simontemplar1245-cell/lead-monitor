"""
Craigslist Scraper
==================
Pulls recent posts from Craigslist "small biz ads" and "services" sections
across target cities via their official RSS feeds.

Why Craigslist still works in 2026:
- Enormous volume of solo-operator service businesses
- Every city has a "small biz ads" section where owners advertise
- Posts often contain phone numbers + email in the body
- RSS is the OFFICIAL data interface — no ToS violation
- Completely free, no API key

RSS URL pattern:
  https://{city}.craigslist.org/search/{section}?format=rss

Sections of interest:
  - sss  → for sale by owner (services are often listed here)
  - bbb  → small biz ads (business opportunities, business for sale)
  - lss  → legal services
  - cps  → computer services
  - lbs  → labor/moving
  - sks  → skilled trades
  - ths  → therapeutic services
  - crs  → creative services
  - evs  → event services
  - bts  → beauty services
  - bfs  → business services
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import Generator
from xml.etree import ElementTree

import requests

from config import CRAIGSLIST

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class CraigslistScraper:
    """Scrapes Craigslist service listings via RSS."""

    def __init__(self):
        self.enabled = CRAIGSLIST.get("enabled", True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })
        self.request_delay = CRAIGSLIST.get("request_delay_seconds", 1.5)

    def scan_all(self) -> Generator[dict, None, None]:
        """Scan every configured (city, section) combo."""
        if not self.enabled:
            return

        cities = CRAIGSLIST.get("cities", [])
        sections = CRAIGSLIST.get("sections", [])

        for city in cities:
            for section in sections:
                feed_url = (
                    f"https://{city}.craigslist.org/search/{section}"
                    f"?format=rss"
                )
                try:
                    yield from self._scan_feed(feed_url, city, section)
                    time.sleep(self.request_delay)
                except Exception as e:
                    logger.warning(
                        f"Craigslist {city}/{section} failed: {e}"
                    )

    def _scan_feed(self, url: str, city: str, section: str
                   ) -> Generator[dict, None, None]:
        """Parse one RSS feed and yield candidate leads."""
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                logger.debug(f"CL feed {url} returned {resp.status_code}")
                return
        except requests.RequestException as e:
            logger.debug(f"CL feed fetch failed: {e}")
            return

        try:
            # Craigslist uses RDF namespace; parse tolerantly
            root = ElementTree.fromstring(resp.content)
        except ElementTree.ParseError as e:
            logger.debug(f"CL RSS parse error for {url}: {e}")
            return

        # RSS 1.0 / RDF namespaces
        ns = {
            "rdf":  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rss":  "http://purl.org/rss/1.0/",
            "dc":   "http://purl.org/dc/elements/1.1/",
        }

        items = root.findall("rss:item", ns)
        if not items:
            items = root.findall(".//item")  # RSS 2.0 fallback

        for item in items:
            title = self._xml_text(item, "rss:title", ns) or \
                    self._xml_text(item, "title", {})
            desc = self._xml_text(item, "rss:description", ns) or \
                   self._xml_text(item, "description", {})
            link = self._xml_text(item, "rss:link", ns) or \
                   self._xml_text(item, "link", {})
            date = self._xml_text(item, "dc:date", ns) or \
                   self._xml_text(item, "pubDate", {})

            if not title or not link:
                continue

            # Craigslist descriptions often contain raw HTML; strip tags
            desc_clean = re.sub(r"<[^>]+>", " ", desc or "").strip()

            post_id = (
                f"cl_{city}_{hashlib.md5(link.encode()).hexdigest()[:16]}"
            )

            yield {
                "post_id": post_id,
                "platform": "craigslist",
                "community": f"{city}/{section}",
                "author": "",  # CL posts are anonymous by design
                "title": title[:200],
                "body": desc_clean[:500],
                "url": link,
                "post_created_at": date or
                    datetime.now(timezone.utc).isoformat(),
                "full_text": f"{title}. {desc_clean}",
            }

    @staticmethod
    def _xml_text(elem, tag, ns) -> str:
        found = elem.find(tag, ns) if ns else elem.find(tag)
        return (found.text or "").strip() if found is not None else ""
