"""
Reddit Scraper
==============
Uses PRAW (Python Reddit API Wrapper) to monitor target subreddits.
Scans both new posts and recent comments for pain-point keywords.

Rate limits: 100 requests/minute on free tier (very generous for our use case).
We scan ~30 subreddits every 30 minutes = well within limits.
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Generator

import praw
from praw.exceptions import RedditAPIException

from config import (
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_USERNAME,
    REDDIT_PASSWORD,
    REDDIT_USER_AGENT,
    SUBREDDITS,
    MAX_POSTS_PER_SUBREDDIT,
    LOOKBACK_HOURS,
)

logger = logging.getLogger(__name__)


class RedditScraper:
    """Monitors Reddit subreddits for potential AI service leads."""

    def __init__(self):
        self.reddit = None
        self.enabled = bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET)

        if self.enabled:
            try:
                self.reddit = praw.Reddit(
                    client_id=REDDIT_CLIENT_ID,
                    client_secret=REDDIT_CLIENT_SECRET,
                    username=REDDIT_USERNAME,
                    password=REDDIT_PASSWORD,
                    user_agent=REDDIT_USER_AGENT,
                )
                # Test connection
                self.reddit.user.me()
                logger.info("Reddit API connected successfully")
            except Exception as e:
                # Try read-only mode (no username/password needed)
                try:
                    self.reddit = praw.Reddit(
                        client_id=REDDIT_CLIENT_ID,
                        client_secret=REDDIT_CLIENT_SECRET,
                        user_agent=REDDIT_USER_AGENT,
                    )
                    logger.info("Reddit API connected in read-only mode")
                except Exception as e2:
                    logger.error(f"Reddit API connection failed: {e2}")
                    self.enabled = False
        else:
            logger.warning(
                "Reddit scraper disabled - set REDDIT_CLIENT_ID and "
                "REDDIT_CLIENT_SECRET in .env"
            )

    def scan_all_subreddits(self) -> Generator[dict, None, None]:
        """
        Scan all configured subreddits across all tiers.
        Yields raw post data for each new post/comment found.
        """
        if not self.enabled:
            logger.warning("Reddit scraper not enabled, skipping")
            return

        all_subs = []
        for tier, subs in SUBREDDITS.items():
            all_subs.extend([(tier, sub) for sub in subs])

        logger.info(f"Scanning {len(all_subs)} subreddits...")

        for tier, subreddit_name in all_subs:
            try:
                yield from self._scan_subreddit(subreddit_name, tier)
                # Small delay between subreddits to be respectful of rate limits
                time.sleep(0.5)
            except RedditAPIException as e:
                logger.error(f"Reddit API error for r/{subreddit_name}: {e}")
                if "429" in str(e):
                    logger.warning("Rate limited - waiting 60 seconds")
                    time.sleep(60)
            except Exception as e:
                logger.error(f"Error scanning r/{subreddit_name}: {e}")

    def _scan_subreddit(self, subreddit_name: str, tier: str) -> Generator[dict, None, None]:
        """Scan a single subreddit for new posts and comments."""
        subreddit = self.reddit.subreddit(subreddit_name)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)

        # Scan new posts
        post_count = 0
        try:
            for submission in subreddit.new(limit=MAX_POSTS_PER_SUBREDDIT):
                post_time = datetime.fromtimestamp(
                    submission.created_utc, tz=timezone.utc
                )

                # Skip posts older than our lookback window
                if post_time < cutoff_time:
                    break

                post_count += 1
                # Combine title and selftext for analysis
                full_text = f"{submission.title}\n{submission.selftext or ''}"

                yield {
                    "post_id": f"reddit_{submission.id}",
                    "platform": "reddit",
                    "community": f"r/{subreddit_name}",
                    "tier": tier,
                    "author": str(submission.author) if submission.author else "[deleted]",
                    "title": submission.title,
                    "body": submission.selftext or "",
                    "full_text": full_text,
                    "url": f"https://reddit.com{submission.permalink}",
                    "post_created_at": post_time.isoformat(),
                    "post_score": submission.score,
                    "num_comments": submission.num_comments,
                    "type": "post",
                }

        except Exception as e:
            logger.error(f"Error fetching posts from r/{subreddit_name}: {e}")

        # Scan recent comments (sometimes people comment on older posts)
        comment_count = 0
        try:
            for comment in subreddit.comments(limit=MAX_POSTS_PER_SUBREDDIT):
                comment_time = datetime.fromtimestamp(
                    comment.created_utc, tz=timezone.utc
                )

                if comment_time < cutoff_time:
                    break

                comment_count += 1
                yield {
                    "post_id": f"reddit_comment_{comment.id}",
                    "platform": "reddit",
                    "community": f"r/{subreddit_name}",
                    "tier": tier,
                    "author": str(comment.author) if comment.author else "[deleted]",
                    "title": "",
                    "body": comment.body or "",
                    "full_text": comment.body or "",
                    "url": f"https://reddit.com{comment.permalink}",
                    "post_created_at": comment_time.isoformat(),
                    "post_score": comment.score,
                    "num_comments": 0,
                    "type": "comment",
                }

        except Exception as e:
            logger.error(f"Error fetching comments from r/{subreddit_name}: {e}")

        logger.info(
            f"r/{subreddit_name} ({tier}): "
            f"scanned {post_count} posts, {comment_count} comments"
        )

    def scan_specific_subreddits(self, subreddit_names: list) -> Generator[dict, None, None]:
        """Scan a specific list of subreddits (useful for testing)."""
        if not self.enabled:
            return

        for name in subreddit_names:
            try:
                yield from self._scan_subreddit(name, "custom")
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Error scanning r/{name}: {e}")
