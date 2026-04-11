"""
Quora Scraper
=============
Quora is hostile to direct scraping — aggressive anti-bot, login-walls on
many pages, JS-heavy rendering. But DuckDuckGo indexes Quora questions
aggressively and returns the question title + an answer snippet, which
is everything we need to spot a buying-intent question.

Strategy:
  For each buying-intent phrase, query DDG with `site:quora.com "phrase"`
  and emit each result as a candidate lead. Classifier decides if it's
  HOT/WARM.

Why this is a good source:
  - People literally ask "what's the best AI receptionist for my dental
    practice" on Quora, and those threads rank on Google for years.
  - Answering in the thread gets you visibility to everyone who searches
    the same question later — it's a compounding SEO play.
  - The asker is a high-intent buyer by definition.
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import Generator
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from config import QUORA

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


class QuoraScraper:
    """Finds Quora questions matching buying-intent queries via DDG."""

    def __init__(self):
        self.enabled = QUORA.get("enabled", True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.max_results_per_query = QUORA.get("max_results_per_query", 6)
        self.request_delay = QUORA.get("request_delay_seconds", 1.5)

    def scan_all(self) -> Generator[dict, None, None]:
        """Run each configured intent query against DDG."""
        if not self.enabled:
            return

        queries = QUORA.get("queries", [])
        seen = set()

        for raw_query in queries:
            ddg_query = f'site:quora.com "{raw_query}"'
            try:
                for result in self._search_ddg(ddg_query):
                    if result["url"] in seen:
                        continue
                    seen.add(result["url"])

                    post_id = (
                        f"quora_{hashlib.md5(result['url'].encode()).hexdigest()[:16]}"
                    )

                    yield {
                        "post_id": post_id,
                        "platform": "quora",
                        "community": "quora",
                        "author": "",
                        "title": result["title"][:200],
                        "body": result["snippet"][:500],
                        "url": result["url"],
                        "post_created_at":
                            datetime.now(timezone.utc).isoformat(),
                        "full_text":
                            f"{raw_query}. {result['title']}. {result['snippet']}",
                    }

                time.sleep(self.request_delay)
            except Exception as e:
                logger.warning(f"Quora query '{raw_query}' failed: {e}")

    def _search_ddg(self, query: str) -> list:
        try:
            resp = self.session.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query},
                headers={"Referer": "https://duckduckgo.com/"},
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
        for div in soup.select("div.result")[: self.max_results_per_query]:
            a = div.select_one("a.result__a")
            if not a:
                continue
            href = a.get("href", "")
            if "uddg=" in href:
                m = re.search(r"uddg=([^&]+)", href)
                if m:
                    href = unquote(m.group(1))
            if not href.startswith("http"):
                continue
            # Only accept real quora URLs (DDG sometimes returns
            # wikipedia or aggregator sites for the same query)
            if "quora.com" not in href:
                continue

            title = a.get_text(" ", strip=True)
            snippet_el = div.select_one(".result__snippet")
            snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
            results.append({"url": href, "title": title, "snippet": snippet})

        return results
