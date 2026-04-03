"""
Hacker News Scraper
===================
Uses the free Algolia API to search Hacker News for relevant posts.
HN is valuable because the audience includes technical founders and
decision-makers who buy or recommend AI services.

API: https://hn.algolia.com/api (completely free, no key needed)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Generator

import requests

from config import HACKERNEWS, LOOKBACK_HOURS

logger = logging.getLogger(__name__)

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"


class HackerNewsScraper:
    """Monitors Hacker News via the free Algolia API."""

    def __init__(self):
        self.enabled = HACKERNEWS.get("enabled", True)
        self.keywords = HACKERNEWS.get("keywords", [])
        self.max_results = HACKERNEWS.get("max_results", 20)

    def scan(self) -> Generator[dict, None, None]:
        """
        Search Hacker News for all configured keywords.
        Yields post data for each match found.
        """
        if not self.enabled:
            logger.info("Hacker News scraper disabled")
            return

        # Calculate time window (unix timestamp)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(LOOKBACK_HOURS, 24))
        cutoff_ts = int(cutoff.timestamp())

        seen_ids = set()

        for keyword in self.keywords:
            try:
                yield from self._search_keyword(keyword, cutoff_ts, seen_ids)
            except Exception as e:
                logger.error(f"HN search error for '{keyword}': {e}")

    def _search_keyword(self, keyword: str, cutoff_ts: int,
                        seen_ids: set) -> Generator[dict, None, None]:
        """Search HN for a single keyword."""
        params = {
            "query": keyword,
            "tags": "(story,comment)",  # Search both stories and comments
            "numericFilters": f"created_at_i>{cutoff_ts}",
            "hitsPerPage": self.max_results,
        }

        try:
            response = requests.get(ALGOLIA_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"HN API request failed: {e}")
            return

        hits = data.get("hits", [])
        logger.info(f"HN search '{keyword}': {len(hits)} results")

        for hit in hits:
            object_id = hit.get("objectID", "")

            # Skip duplicates (same post might match multiple keywords)
            if object_id in seen_ids:
                continue
            seen_ids.add(object_id)

            # Extract content based on type
            if hit.get("_tags", []) and "story" in hit.get("_tags", []):
                title = hit.get("title", "")
                body = hit.get("story_text", "") or ""
                url = hit.get("url", "") or f"https://news.ycombinator.com/item?id={object_id}"
                hn_url = f"https://news.ycombinator.com/item?id={object_id}"
            else:
                # Comment
                title = ""
                body = hit.get("comment_text", "") or ""
                # Strip HTML tags from comments
                body = self._strip_html(body)
                parent_id = hit.get("story_id", object_id)
                url = f"https://news.ycombinator.com/item?id={object_id}"
                hn_url = url

            full_text = f"{title} {body}".strip()
            if not full_text:
                continue

            # Parse creation time
            created_at = hit.get("created_at", "")

            yield {
                "post_id": f"hn_{object_id}",
                "platform": "hackernews",
                "community": "Hacker News",
                "author": hit.get("author", "Unknown"),
                "title": title,
                "body": body[:2000],
                "full_text": full_text[:2000],
                "url": hn_url,
                "post_created_at": created_at,
                "post_score": hit.get("points", 0) or 0,
                "num_comments": hit.get("num_comments", 0) or 0,
                "type": "story" if title else "comment",
            }

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags from text."""
        import re
        clean = re.sub(r'<[^>]+>', ' ', text)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()
