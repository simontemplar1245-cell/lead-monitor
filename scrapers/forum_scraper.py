"""
Forum Scraper
=============
Scrapes industry-specific forums using BeautifulSoup and Playwright.
These forums are the hidden gems - virtually zero AI marketing competition.

Target forums:
- Dentaltown.com (250k dental professionals)
- ContractorTalk.com (contractor business forum)
- HVACTalk.com (HVAC professionals)
- LawnSite.com (lawn/landscaping business)
- Insurance-Forums.com (insurance agents)

Strategy: We check the "recent posts" or "new posts" section of each forum
for threads containing our pain-point keywords. Forums are slower-moving
than Reddit, so posts stay relevant for days/weeks.
"""

import time
import hashlib
import logging
from datetime import datetime, timezone
from typing import Generator, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import FORUMS, ALL_KEYWORDS

logger = logging.getLogger(__name__)

# Common headers to look like a real browser
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class ForumScraper:
    """Scrapes industry-specific forums for potential leads."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def scan_all_forums(self) -> Generator[dict, None, None]:
        """Scan all enabled forums."""
        for forum_id, forum_config in FORUMS.items():
            if not forum_config.get("enabled", False):
                continue

            logger.info(f"Scanning forum: {forum_config['name']}")

            try:
                if forum_config.get("scraper") == "playwright":
                    yield from self._scan_with_playwright(forum_id, forum_config)
                else:
                    yield from self._scan_with_beautifulsoup(forum_id, forum_config)

                # Be respectful - wait between forums
                time.sleep(3)

            except Exception as e:
                logger.error(f"Error scanning {forum_config['name']}: {e}")

    def _scan_with_beautifulsoup(self, forum_id: str,
                                  config: dict) -> Generator[dict, None, None]:
        """Scrape a forum using requests + BeautifulSoup (for static HTML forums)."""
        forum_url = config.get("forum_url", config["base_url"])

        try:
            response = self.session.get(forum_url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {forum_url}: {e}")
            return

        soup = BeautifulSoup(response.text, "lxml")

        # Extract thread links and titles
        # Forums use various HTML structures, so we try multiple selectors
        threads = self._extract_threads(soup, config)

        found = 0
        for thread in threads:
            title = thread.get("title", "")
            url = thread.get("url", "")

            if not title or not url:
                continue

            # Make URL absolute
            if not url.startswith("http"):
                url = urljoin(config["base_url"], url)

            # Quick keyword check on title
            title_lower = title.lower()
            matched_keyword = None
            for kw in ALL_KEYWORDS:
                if kw.lower() in title_lower:
                    matched_keyword = kw
                    break

            if not matched_keyword:
                continue

            # Generate a unique post ID from the URL
            post_id = f"forum_{forum_id}_{hashlib.md5(url.encode()).hexdigest()[:12]}"

            found += 1
            yield {
                "post_id": post_id,
                "platform": "forum",
                "community": config["name"],
                "author": thread.get("author", "Unknown"),
                "title": title,
                "body": thread.get("preview", ""),
                "full_text": f"{title} {thread.get('preview', '')}",
                "url": url,
                "post_created_at": thread.get("date", datetime.now(timezone.utc).isoformat()),
                "type": "forum_thread",
            }

        logger.info(f"{config['name']}: found {found} keyword-matching threads")

    def _extract_threads(self, soup: BeautifulSoup, config: dict) -> list:
        """
        Extract thread titles and URLs from a forum page.
        Handles multiple forum software formats (vBulletin, XenForo, phpBB, etc.)
        """
        threads = []

        # =====================================================================
        # XenForo format (used by ContractorTalk, LawnSite, many modern forums)
        # =====================================================================
        xenforo_threads = soup.select(".structItem-title a, .listBlock.main a.PreviewTooltip")
        if xenforo_threads:
            for link in xenforo_threads:
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if title and href and len(title) > 5:
                    threads.append({"title": title, "url": href})

        # =====================================================================
        # vBulletin format (used by HVACTalk, many older forums)
        # =====================================================================
        if not threads:
            vb_threads = soup.select(
                "#threads .threadtitle a, "
                ".threads .title a, "
                "a.topictitle, "
                ".threadbit .title a"
            )
            for link in vb_threads:
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if title and href and len(title) > 5:
                    threads.append({"title": title, "url": href})

        # =====================================================================
        # phpBB format
        # =====================================================================
        if not threads:
            phpbb_threads = soup.select(".topictitle, .topic-title a")
            for link in phpbb_threads:
                title = link.get_text(strip=True)
                href = link.get("href", "")
                if title and href:
                    threads.append({"title": title, "url": href})

        # =====================================================================
        # Generic fallback - look for any link with substantial text
        # =====================================================================
        if not threads:
            all_links = soup.find_all("a", href=True)
            for link in all_links:
                title = link.get_text(strip=True)
                href = link.get("href", "")
                # Filter for thread-like links (have text, look like thread URLs)
                if (title and len(title) > 15 and
                    any(kw in href.lower() for kw in
                        ["thread", "topic", "post", "discussion", "showthread"])):
                    threads.append({"title": title, "url": href})

        return threads[:50]  # Cap to prevent scanning too many

    def _scan_with_playwright(self, forum_id: str,
                               config: dict) -> Generator[dict, None, None]:
        """
        Scrape a JS-heavy forum using Playwright.
        Used for sites like Dentaltown that require JavaScript rendering.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning(
                f"Playwright not installed - skipping {config['name']}. "
                "Run: pip install playwright && playwright install chromium"
            )
            return

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=HEADERS["User-Agent"],
                    viewport={"width": 1280, "height": 800},
                )
                page = context.new_page()

                # Navigate to forum
                forum_url = config.get("search_url", config.get("forum_url", config["base_url"]))
                page.goto(forum_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)  # Let JS render

                # Get page content after JS rendering
                content = page.content()
                soup = BeautifulSoup(content, "lxml")

                # Extract threads same as BeautifulSoup
                threads = self._extract_threads(soup, config)

                found = 0
                for thread in threads:
                    title = thread.get("title", "")
                    url = thread.get("url", "")

                    if not title or not url:
                        continue

                    if not url.startswith("http"):
                        url = urljoin(config["base_url"], url)

                    # Keyword check
                    title_lower = title.lower()
                    matched = False
                    for kw in ALL_KEYWORDS:
                        if kw.lower() in title_lower:
                            matched = True
                            break

                    if not matched:
                        continue

                    post_id = f"forum_{forum_id}_{hashlib.md5(url.encode()).hexdigest()[:12]}"

                    found += 1
                    yield {
                        "post_id": post_id,
                        "platform": "forum",
                        "community": config["name"],
                        "author": thread.get("author", "Unknown"),
                        "title": title,
                        "body": thread.get("preview", ""),
                        "full_text": f"{title} {thread.get('preview', '')}",
                        "url": url,
                        "post_created_at": datetime.now(timezone.utc).isoformat(),
                        "type": "forum_thread",
                    }

                logger.info(f"{config['name']} (Playwright): found {found} matching threads")
                browser.close()

        except Exception as e:
            logger.error(f"Playwright error for {config['name']}: {e}")

    def scrape_thread_content(self, url: str) -> Optional[str]:
        """
        Fetch the full content of a specific forum thread.
        Used for deeper analysis of promising threads.
        """
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "lxml")

            # Extract main post content
            content_selectors = [
                ".message-body",          # XenForo
                ".postcontent",           # vBulletin
                ".postbody",              # phpBB
                ".post_body",             # Generic
                "article",               # Modern
                ".entry-content",        # WordPress-based
            ]

            for selector in content_selectors:
                content = soup.select_one(selector)
                if content:
                    return content.get_text(strip=True)[:3000]

            return None

        except Exception as e:
            logger.error(f"Error fetching thread {url}: {e}")
            return None
