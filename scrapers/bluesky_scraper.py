"""
Bluesky Scraper
===============
Uses the public Bluesky API (AT Protocol) to search for relevant posts.
Bluesky is a hidden gem: 40M+ users, tech-savvy audience, open API,
and virtually no automated monitoring competition.

API: https://public.api.bsky.app (free, no auth needed for search)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Generator

import requests

from config import BLUESKY, LOOKBACK_HOURS

logger = logging.getLogger(__name__)


class BlueskyScraper:
    """Monitors Bluesky for potential leads via the public AT Protocol API."""

    def __init__(self):
        self.enabled = BLUESKY.get("enabled", True)
        self.api_url = BLUESKY.get("api_url", "https://public.api.bsky.app")
        self.keywords = BLUESKY.get("keywords", [])
        self.max_results = BLUESKY.get("max_results", 25)

    def scan(self) -> Generator[dict, None, None]:
        """
        Search Bluesky for all configured keywords.
        Yields post data for each match found.
        """
        if not self.enabled:
            logger.info("Bluesky scraper disabled")
            return

        seen_uris = set()

        for keyword in self.keywords:
            try:
                yield from self._search_keyword(keyword, seen_uris)
            except Exception as e:
                logger.error(f"Bluesky search error for '{keyword}': {e}")

    def _search_keyword(self, keyword: str,
                        seen_uris: set) -> Generator[dict, None, None]:
        """Search Bluesky for a single keyword using the search API."""
        url = f"{self.api_url}/xrpc/app.bsky.feed.searchPosts"
        params = {
            "q": keyword,
            "limit": min(self.max_results, 25),  # API max is 25 per request
            "sort": "latest",
        }

        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"Bluesky API request failed: {e}")
            return

        posts = data.get("posts", [])
        logger.info(f"Bluesky search '{keyword}': {len(posts)} results")

        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(LOOKBACK_HOURS, 24))

        for post in posts:
            try:
                uri = post.get("uri", "")

                # Skip duplicates
                if uri in seen_uris:
                    continue
                seen_uris.add(uri)

                # Extract post data
                record = post.get("record", {})
                text = record.get("text", "")
                created_at_str = record.get("createdAt", "")

                if not text:
                    continue

                # Check if post is within our time window
                if created_at_str:
                    try:
                        created_at = datetime.fromisoformat(
                            created_at_str.replace("Z", "+00:00")
                        )
                        if created_at < cutoff:
                            continue
                    except (ValueError, TypeError):
                        pass

                # Extract author info
                author = post.get("author", {})
                handle = author.get("handle", "unknown")
                display_name = author.get("displayName", handle)

                # Build Bluesky web URL from AT URI
                # URI format: at://did:plc:xxx/app.bsky.feed.post/yyy
                parts = uri.split("/")
                if len(parts) >= 5:
                    post_rkey = parts[-1]
                    web_url = f"https://bsky.app/profile/{handle}/post/{post_rkey}"
                else:
                    web_url = f"https://bsky.app/profile/{handle}"

                # Get engagement metrics
                like_count = post.get("likeCount", 0)
                reply_count = post.get("replyCount", 0)
                repost_count = post.get("repostCount", 0)

                yield {
                    "post_id": f"bsky_{uri.split('/')[-1] if '/' in uri else uri[:20]}",
                    "platform": "bluesky",
                    "community": "Bluesky",
                    "author": f"{display_name} (@{handle})",
                    "title": "",
                    "body": text[:2000],
                    "full_text": text[:2000],
                    "url": web_url,
                    "post_created_at": created_at_str,
                    "post_score": like_count,
                    "num_comments": reply_count,
                    "type": "post",
                }

            except Exception as e:
                logger.error(f"Error parsing Bluesky post: {e}")
                continue
