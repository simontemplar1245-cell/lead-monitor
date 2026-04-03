"""
Reddit Scraper
==============
Uses Reddit's public JSON endpoints - NO API KEY REQUIRED.
Reddit exposes public subreddit data at:
  https://www.reddit.com/r/subredditname/new.json

This is perfectly valid for read-only monitoring at low frequency.
Rate limit: ~1 request per 2 seconds per IP (we stay well within this).

No PRAW, no OAuth, no API registration needed.
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Generator

import requests

from config import (
    SUBREDDITS,
    MAX_POSTS_PER_SUBREDDIT,
    LOOKBACK_HOURS,
    REDDIT_USER_AGENT,
)

logger = logging.getLogger(__name__)

REDDIT_JSON_URL = "https://www.reddit.com/r/{subreddit}/new.json"

HEADERS = {
    "User-Agent": REDDIT_USER_AGENT,
    "Accept": "application/json",
}


class RedditScraper:
    """
    Monitors Reddit subreddits using public JSON endpoints.
    No API key or account required.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.enabled = True
        logger.info("Reddit scraper initialised (public JSON mode - no API key needed)")

    def scan_all_subreddits(self) -> Generator[dict, None, None]:
        """
        Scan all configured subreddits across all tiers.
        Yields raw post data for each new post found.
        """
        all_subs = []
        for tier, subs in SUBREDDITS.items():
            all_subs.extend([(tier, sub) for sub in subs])

        logger.info(f"Scanning {len(all_subs)} subreddits via public JSON...")

        for tier, subreddit_name in all_subs:
            try:
                yield from self._scan_subreddit(subreddit_name, tier)
                # Reddit rate limit: stay under 1 req/sec to be safe
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error scanning r/{subreddit_name}: {e}")

    def _scan_subreddit(self, subreddit_name: str,
                        tier: str) -> Generator[dict, None, None]:
        """Fetch new posts from a single subreddit using the public JSON API."""
        url = REDDIT_JSON_URL.format(subreddit=subreddit_name)
        params = {"limit": MAX_POSTS_PER_SUBREDDIT}
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

        try:
            response = self.session.get(url, params=params, timeout=15)

            # Handle private/banned/non-existent subreddits gracefully
            if response.status_code == 404:
                logger.warning(f"r/{subreddit_name} not found (404) - skipping")
                return
            if response.status_code == 403:
                logger.warning(f"r/{subreddit_name} is private (403) - skipping")
                return
            if response.status_code == 429:
                logger.warning("Reddit rate limited - waiting 60 seconds")
                time.sleep(60)
                return

            response.raise_for_status()
            data = response.json()

        except requests.RequestException as e:
            logger.error(f"Request failed for r/{subreddit_name}: {e}")
            return
        except ValueError as e:
            logger.error(f"JSON parse error for r/{subreddit_name}: {e}")
            return

        posts = data.get("data", {}).get("children", [])
        post_count = 0

        for post_wrapper in posts:
            post = post_wrapper.get("data", {})

            # Skip stickied/pinned mod posts
            if post.get("stickied", False):
                continue

            created_utc = post.get("created_utc", 0)
            post_time = datetime.fromtimestamp(created_utc, tz=timezone.utc)

            # Only look at posts within our lookback window
            if post_time < cutoff_time:
                continue

            post_count += 1
            post_id = post.get("id", "")
            title = post.get("title", "")
            selftext = post.get("selftext", "") or ""
            permalink = post.get("permalink", "")

            # Skip deleted posts
            if selftext in ("[deleted]", "[removed]"):
                selftext = ""

            full_text = f"{title}\n{selftext}".strip()

            yield {
                "post_id": f"reddit_{post_id}",
                "platform": "reddit",
                "community": f"r/{subreddit_name}",
                "tier": tier,
                "author": post.get("author", "[deleted]"),
                "title": title,
                "body": selftext,
                "full_text": full_text,
                "url": f"https://reddit.com{permalink}",
                "post_created_at": post_time.isoformat(),
                "post_score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "type": "post",
            }

            # Also check top-level comments on highly active posts
            if post.get("num_comments", 0) > 5:
                yield from self._get_post_comments(post_id, subreddit_name,
                                                    tier, cutoff_time)

        logger.info(
            f"r/{subreddit_name} ({tier}): {post_count} new posts scanned"
        )

    def _get_post_comments(self, post_id: str, subreddit_name: str,
                           tier: str,
                           cutoff_time: datetime) -> Generator[dict, None, None]:
        """Fetch top-level comments from a specific post."""
        url = f"https://www.reddit.com/r/{subreddit_name}/comments/{post_id}.json"

        try:
            time.sleep(2)  # Rate limit
            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                return
            data = response.json()
        except Exception:
            return

        if len(data) < 2:
            return

        comments_data = data[1].get("data", {}).get("children", [])

        for comment_wrapper in comments_data[:10]:  # Top 10 comments only
            comment = comment_wrapper.get("data", {})

            # Skip non-comment types (e.g. "more" type)
            if comment_wrapper.get("kind") != "t1":
                continue

            body = comment.get("body", "") or ""
            if body in ("[deleted]", "[removed]", ""):
                continue

            created_utc = comment.get("created_utc", 0)
            comment_time = datetime.fromtimestamp(created_utc, tz=timezone.utc)

            if comment_time < cutoff_time:
                continue

            comment_id = comment.get("id", "")
            permalink = comment.get("permalink", "")

            yield {
                "post_id": f"reddit_comment_{comment_id}",
                "platform": "reddit",
                "community": f"r/{subreddit_name}",
                "tier": tier,
                "author": comment.get("author", "[deleted]"),
                "title": "",
                "body": body,
                "full_text": body,
                "url": f"https://reddit.com{permalink}" if permalink else
                       f"https://reddit.com/r/{subreddit_name}/comments/{post_id}",
                "post_created_at": comment_time.isoformat(),
                "post_score": comment.get("score", 0),
                "num_comments": 0,
                "type": "comment",
            }

    def scan_specific_subreddits(self, subreddit_names: list) -> Generator[dict, None, None]:
        """Scan a specific list of subreddits (useful for testing)."""
        for name in subreddit_names:
            try:
                yield from self._scan_subreddit(name, "custom")
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error scanning r/{name}: {e}")
