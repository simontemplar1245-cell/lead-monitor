"""
Reddit Search Scraper
=====================
Searches within our highest-value subreddits for high-intent buyer queries.

Reddit blocks its global /search.json from datacenter IPs (403 Blocked),
but per-subreddit search works fine:
    /r/{subreddit}/search.json?q=QUERY&restrict_sr=1

We search a curated list of the best buyer-dense subreddits for queries
like "virtual receptionist", "chatbot recommendation", etc.
"""

import time
import logging
from datetime import datetime, timezone
from typing import Generator

import requests

from config import REDDIT_SEARCH, REDDIT_USER_AGENT

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": REDDIT_USER_AGENT,
    "Accept": "application/json",
}

# High-value subreddits to search within. These are the ones most likely
# to contain buyer-intent posts about virtual receptionists / chatbots.
# We don't search ALL 80+ subreddits (too slow) — just the top 12.
SEARCH_SUBREDDITS = [
    "smallbusiness",
    "Entrepreneur",
    "sweatystartup",
    "Dentistry",
    "Lawyertalk",
    "LawFirm",
    "realtors",
    "HVAC",
    "plumbing",
    "electricians",
    "restaurantowners",
    "PropertyManagement",
]


class RedditSearchScraper:
    """
    Searches within top subreddits for high-intent buyer queries.
    Uses per-subreddit search endpoint (not blocked from datacenter IPs).
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
            f"Reddit search scraper initialised: {len(self.queries)} queries "
            f"x {len(SEARCH_SUBREDDITS)} subreddits"
        )

    def scan(self) -> Generator[dict, None, None]:
        """Run all search queries across all target subreddits."""
        if not self.enabled or not self.queries:
            logger.info("Reddit search scraper disabled or no queries configured")
            return

        seen_ids = set()

        for subreddit in SEARCH_SUBREDDITS:
            for query in self.queries:
                try:
                    yield from self._search(subreddit, query, seen_ids)
                    time.sleep(2)  # Reddit rate limit
                except Exception as e:
                    logger.error(
                        f"Reddit search error for '{query}' in r/{subreddit}: {e}"
                    )

    def _search(self, subreddit: str, query: str,
                seen_ids: set) -> Generator[dict, None, None]:
        """Run one per-subreddit search and yield normalized post dicts."""
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {
            "q": query,
            "sort": self.sort,
            "t": self.time_filter,
            "limit": self.results_per_query,
            "restrict_sr": 1,  # search within this subreddit only
            "type": "link",
        }

        try:
            response = self.session.get(url, params=params, timeout=15)

            if response.status_code == 429:
                logger.warning("Reddit search rate limited — waiting 60s")
                time.sleep(60)
                return
            if response.status_code in (403, 404):
                # Subreddit private/banned or endpoint blocked — skip
                logger.debug(
                    f"r/{subreddit} search returned {response.status_code}"
                )
                return

            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(
                f"Reddit search request failed for '{query}' in "
                f"r/{subreddit}: {e}"
            )
            return
        except ValueError as e:
            logger.error(f"Reddit search JSON parse error: {e}")
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
            num_comments = post.get("num_comments", 0)

            if selftext in ("[deleted]", "[removed]"):
                selftext = ""

            full_text = f"{title}\n{selftext}".strip()
            count += 1

            yield {
                "post_id": f"reddit_search_{post_id}",
                "platform": "reddit_search",
                "community": f"r/{subreddit} (search: {query[:25]})",
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

        if count > 0:
            logger.info(
                f"Reddit search r/{subreddit} '{query}': {count} results"
            )
