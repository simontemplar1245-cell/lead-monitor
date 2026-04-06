"""
Reddit Search Scraper
=====================
Searches ALL of Reddit (reddit.com/search) for high-intent buyer queries.

Unlike the subreddit scraper (which monitors specific communities for pain
signals), this searches the entire site for people who are actively looking
to BUY a solution — e.g. "virtual receptionist recommendation", "best
chatbot for small business".

Uses Reddit's public JSON search endpoint. No API key needed.
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Generator

import requests

from config import REDDIT_SEARCH, REDDIT_USER_AGENT

logger = logging.getLogger(__name__)

REDDIT_SEARCH_URL = "https://www.reddit.com/search.json"

HEADERS = {
    "User-Agent": REDDIT_USER_AGENT,
    "Accept": "application/json",
}


class RedditSearchScraper:
    """
    Searches all of Reddit for high-intent buyer queries.
    No API key or account required.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.enabled = REDDIT_SEARCH.get("enabled", True)
        self.queries = REDDIT_SEARCH.get("queries", [])
        self.sort = REDDIT_SEARCH.get("sort", "new")
        self.time_filter = REDDIT_SEARCH.get("time_filter", "week")
        self.results_per_query = REDDIT_SEARCH.get("results_per_query", 10)
        logger.info(
            f"Reddit search scraper initialised: {len(self.queries)} queries"
        )

    def scan(self) -> Generator[dict, None, None]:
        """
        Run all search queries and yield post data for each result.
        """
        if not self.enabled or not self.queries:
            logger.info("Reddit search scraper disabled or no queries configured")
            return

        seen_ids = set()

        for query in self.queries:
            try:
                yield from self._search(query, seen_ids)
                # Reddit rate limit: stay under 1 req/sec
                time.sleep(2)
            except Exception as e:
                logger.error(f"Reddit search error for '{query}': {e}")

    def _search(self, query: str, seen_ids: set) -> Generator[dict, None, None]:
        """Run one Reddit search and yield normalized post dicts."""
        params = {
            "q": query,
            "sort": self.sort,
            "t": self.time_filter,
            "limit": self.results_per_query,
            "type": "link",  # only posts, not comments
        }

        try:
            response = self.session.get(
                REDDIT_SEARCH_URL, params=params, timeout=15
            )

            if response.status_code == 429:
                logger.warning("Reddit search rate limited — waiting 60s")
                time.sleep(60)
                return

            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"Reddit search request failed for '{query}': {e}")
            return
        except ValueError as e:
            logger.error(f"Reddit search JSON parse error for '{query}': {e}")
            return

        posts = data.get("data", {}).get("children", [])
        count = 0

        for post_wrapper in posts:
            post = post_wrapper.get("data", {})

            if post.get("stickied", False):
                continue

            post_id = post.get("id", "")
            if not post_id or post_id in seen_ids:
                continue
            seen_ids.add(post_id)

            created_utc = post.get("created_utc", 0)
            post_time = datetime.fromtimestamp(created_utc, tz=timezone.utc)

            title = post.get("title", "")
            selftext = post.get("selftext", "") or ""
            permalink = post.get("permalink", "")
            subreddit = post.get("subreddit", "unknown")
            num_comments = post.get("num_comments", 0)

            if selftext in ("[deleted]", "[removed]"):
                selftext = ""

            full_text = f"{title}\n{selftext}".strip()
            count += 1

            yield {
                "post_id": f"reddit_search_{post_id}",
                "platform": "reddit_search",
                "community": f"r/{subreddit} (via search: {query[:30]})",
                "tier": "search",
                "author": post.get("author", "[deleted]"),
                "title": title,
                "body": selftext,
                "full_text": full_text,
                "url": f"https://reddit.com{permalink}",
                "post_created_at": post_time.isoformat(),
                "post_score": post.get("score", 0),
                "num_comments": num_comments,
                "type": "post",
            }

        logger.info(f"Reddit search '{query}': {count} results")
