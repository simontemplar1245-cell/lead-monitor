"""
Lead Monitor - Main Entry Point
================================
Orchestrates the full scanning pipeline:
1. Run all scrapers (Reddit, forums, HN, Bluesky)
2. Pre-filter with keywords
3. Classify with Claude Haiku
4. Save to database
5. Send Telegram alerts for HOT leads

Usage:
  python main.py              # Run a full scan cycle
  python main.py --reddit     # Reddit only
  python main.py --forums     # Forums only
  python main.py --hn         # Hacker News only
  python main.py --bluesky    # Bluesky only
  python main.py --test       # Dry run (no notifications)
  python main.py --digest     # Send daily digest
"""

import sys
import os
import time
import argparse
import logging
from datetime import datetime, timezone

# Ensure we can import from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import LOG_LEVEL, LOG_FILE, DATABASE_PATH, HOT_THRESHOLD, WARM_THRESHOLD
from core.database import LeadDatabase
from core.classifier import LeadClassifier
from core.notifier import TelegramNotifier

# =============================================================================
# LOGGING SETUP
# =============================================================================
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("lead_monitor")


def run_reddit_scan(db: LeadDatabase, classifier: LeadClassifier,
                    notifier: TelegramNotifier, test_mode: bool = False) -> dict:
    """Run Reddit scraper across all target subreddits."""
    from scrapers.reddit_scraper import RedditScraper

    stats = {"scanned": 0, "found": 0, "hot": 0, "warm": 0, "cold": 0, "errors": ""}
    start_time = time.time()

    try:
        scraper = RedditScraper()
        if not scraper.enabled:
            stats["errors"] = "Reddit scraper not configured"
            return stats

        for post_data in scraper.scan_all_subreddits():
            stats["scanned"] += 1

            # Check for duplicate
            if db.is_duplicate(post_data["post_id"]):
                continue

            # Classify the post
            text = post_data.get("full_text", "")
            classification = classifier.classify(
                text,
                platform=post_data.get("platform", ""),
                community=post_data.get("community", ""),
            )

            # Skip cold leads that didn't even match keywords
            if classification["category"] == "COLD" and not classification.get("keyword_matched"):
                continue

            # Merge classification into post data
            lead_data = {**post_data, **classification}

            # Save to database
            lead_id = db.save_lead(lead_data)
            if lead_id is None:
                continue

            stats["found"] += 1

            # Track by category
            if classification["category"] == "HOT":
                stats["hot"] += 1
                if not test_mode:
                    notifier.send_hot_alert(lead_data)
            elif classification["category"] == "WARM":
                stats["warm"] += 1
                if not test_mode:
                    notifier.send_warm_alert(lead_data)
            else:
                stats["cold"] += 1

    except Exception as e:
        stats["errors"] = str(e)
        logger.error(f"Reddit scan error: {e}", exc_info=True)

    duration = time.time() - start_time
    db.log_scan("reddit", "all", stats["scanned"], stats["found"],
                stats["hot"], stats["warm"], stats["cold"],
                stats["errors"], duration)

    logger.info(
        f"Reddit scan complete: {stats['scanned']} scanned, "
        f"{stats['found']} leads ({stats['hot']} hot, {stats['warm']} warm) "
        f"in {duration:.1f}s"
    )
    return stats


def run_forum_scan(db: LeadDatabase, classifier: LeadClassifier,
                   notifier: TelegramNotifier, test_mode: bool = False) -> dict:
    """Run forum scrapers (Dentaltown, ContractorTalk, etc.)."""
    from scrapers.forum_scraper import ForumScraper

    stats = {"scanned": 0, "found": 0, "hot": 0, "warm": 0, "cold": 0, "errors": ""}
    start_time = time.time()

    try:
        scraper = ForumScraper()

        for post_data in scraper.scan_all_forums():
            stats["scanned"] += 1

            if db.is_duplicate(post_data["post_id"]):
                continue

            text = post_data.get("full_text", "")
            classification = classifier.classify(
                text,
                platform=post_data.get("platform", ""),
                community=post_data.get("community", ""),
            )

            if classification["category"] == "COLD" and not classification.get("keyword_matched"):
                continue

            lead_data = {**post_data, **classification}
            lead_id = db.save_lead(lead_data)
            if lead_id is None:
                continue

            stats["found"] += 1

            if classification["category"] == "HOT":
                stats["hot"] += 1
                if not test_mode:
                    notifier.send_hot_alert(lead_data)
            elif classification["category"] == "WARM":
                stats["warm"] += 1
                if not test_mode:
                    notifier.send_warm_alert(lead_data)
            else:
                stats["cold"] += 1

    except Exception as e:
        stats["errors"] = str(e)
        logger.error(f"Forum scan error: {e}", exc_info=True)

    duration = time.time() - start_time
    db.log_scan("forum", "all", stats["scanned"], stats["found"],
                stats["hot"], stats["warm"], stats["cold"],
                stats["errors"], duration)

    logger.info(
        f"Forum scan complete: {stats['scanned']} scanned, "
        f"{stats['found']} leads ({stats['hot']} hot, {stats['warm']} warm) "
        f"in {duration:.1f}s"
    )
    return stats


def run_hackernews_scan(db: LeadDatabase, classifier: LeadClassifier,
                        notifier: TelegramNotifier, test_mode: bool = False) -> dict:
    """Run Hacker News scraper."""
    from scrapers.hackernews_scraper import HackerNewsScraper

    stats = {"scanned": 0, "found": 0, "hot": 0, "warm": 0, "cold": 0, "errors": ""}
    start_time = time.time()

    try:
        scraper = HackerNewsScraper()

        for post_data in scraper.scan():
            stats["scanned"] += 1

            if db.is_duplicate(post_data["post_id"]):
                continue

            text = post_data.get("full_text", "")
            classification = classifier.classify(
                text,
                platform=post_data.get("platform", ""),
                community=post_data.get("community", ""),
            )

            if classification["category"] == "COLD" and not classification.get("keyword_matched"):
                continue

            lead_data = {**post_data, **classification}
            lead_id = db.save_lead(lead_data)
            if lead_id is None:
                continue

            stats["found"] += 1

            if classification["category"] == "HOT":
                stats["hot"] += 1
                if not test_mode:
                    notifier.send_hot_alert(lead_data)
            elif classification["category"] == "WARM":
                stats["warm"] += 1
                if not test_mode:
                    notifier.send_warm_alert(lead_data)
            else:
                stats["cold"] += 1

    except Exception as e:
        stats["errors"] = str(e)
        logger.error(f"HN scan error: {e}", exc_info=True)

    duration = time.time() - start_time
    db.log_scan("hackernews", "Hacker News", stats["scanned"], stats["found"],
                stats["hot"], stats["warm"], stats["cold"],
                stats["errors"], duration)

    logger.info(
        f"HN scan complete: {stats['scanned']} scanned, "
        f"{stats['found']} leads ({stats['hot']} hot, {stats['warm']} warm) "
        f"in {duration:.1f}s"
    )
    return stats


def run_bluesky_scan(db: LeadDatabase, classifier: LeadClassifier,
                     notifier: TelegramNotifier, test_mode: bool = False) -> dict:
    """Run Bluesky scraper."""
    from scrapers.bluesky_scraper import BlueskyScraper

    stats = {"scanned": 0, "found": 0, "hot": 0, "warm": 0, "cold": 0, "errors": ""}
    start_time = time.time()

    try:
        scraper = BlueskyScraper()

        for post_data in scraper.scan():
            stats["scanned"] += 1

            if db.is_duplicate(post_data["post_id"]):
                continue

            text = post_data.get("full_text", "")
            classification = classifier.classify(
                text,
                platform=post_data.get("platform", ""),
                community=post_data.get("community", ""),
            )

            if classification["category"] == "COLD" and not classification.get("keyword_matched"):
                continue

            lead_data = {**post_data, **classification}
            lead_id = db.save_lead(lead_data)
            if lead_id is None:
                continue

            stats["found"] += 1

            if classification["category"] == "HOT":
                stats["hot"] += 1
                if not test_mode:
                    notifier.send_hot_alert(lead_data)
            elif classification["category"] == "WARM":
                stats["warm"] += 1
                if not test_mode:
                    notifier.send_warm_alert(lead_data)
            else:
                stats["cold"] += 1

    except Exception as e:
        stats["errors"] = str(e)
        logger.error(f"Bluesky scan error: {e}", exc_info=True)

    duration = time.time() - start_time
    db.log_scan("bluesky", "Bluesky", stats["scanned"], stats["found"],
                stats["hot"], stats["warm"], stats["cold"],
                stats["errors"], duration)

    logger.info(
        f"Bluesky scan complete: {stats['scanned']} scanned, "
        f"{stats['found']} leads ({stats['hot']} hot, {stats['warm']} warm) "
        f"in {duration:.1f}s"
    )
    return stats


def run_full_scan(test_mode: bool = False):
    """Run a complete scan cycle across all platforms."""
    logger.info("=" * 60)
    logger.info("Starting full scan cycle")
    logger.info(f"Time: {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"Test mode: {test_mode}")
    logger.info("=" * 60)

    start_time = time.time()

    # Initialize core components
    db = LeadDatabase(DATABASE_PATH)
    classifier = LeadClassifier()
    notifier = TelegramNotifier()

    # Run all scrapers
    all_stats = {}

    logger.info("--- Reddit Scan ---")
    all_stats["reddit"] = run_reddit_scan(db, classifier, notifier, test_mode)

    logger.info("--- Forum Scan ---")
    all_stats["forums"] = run_forum_scan(db, classifier, notifier, test_mode)

    logger.info("--- Hacker News Scan ---")
    all_stats["hackernews"] = run_hackernews_scan(db, classifier, notifier, test_mode)

    logger.info("--- Bluesky Scan ---")
    all_stats["bluesky"] = run_bluesky_scan(db, classifier, notifier, test_mode)

    # Summary
    total_time = time.time() - start_time
    total_scanned = sum(s["scanned"] for s in all_stats.values())
    total_found = sum(s["found"] for s in all_stats.values())
    total_hot = sum(s["hot"] for s in all_stats.values())
    total_warm = sum(s["warm"] for s in all_stats.values())
    total_errors = [f"{k}: {v['errors']}" for k, v in all_stats.items() if v.get("errors")]

    logger.info("=" * 60)
    logger.info(f"SCAN COMPLETE in {total_time:.1f}s")
    logger.info(f"Total scanned: {total_scanned}")
    logger.info(f"Total leads: {total_found} ({total_hot} HOT, {total_warm} WARM)")
    if total_errors:
        logger.warning(f"Errors: {'; '.join(total_errors)}")
    logger.info("=" * 60)

    # Send error alert if critical issues
    if total_errors and not test_mode:
        notifier.send_error_alert(f"Scan completed with errors: {'; '.join(total_errors)}")

    return all_stats


def send_daily_digest():
    """Send the daily summary digest via Telegram."""
    db = LeadDatabase(DATABASE_PATH)
    notifier = TelegramNotifier()

    stats = db.get_stats_summary(days=1)
    sources = db.get_platform_stats(days=1)

    notifier.send_daily_digest(stats, sources)
    logger.info("Daily digest sent")


def main():
    parser = argparse.ArgumentParser(description="Lead Monitor for Advance AI Services")
    parser.add_argument("--reddit", action="store_true", help="Run Reddit scan only")
    parser.add_argument("--forums", action="store_true", help="Run forum scan only")
    parser.add_argument("--hn", action="store_true", help="Run Hacker News scan only")
    parser.add_argument("--bluesky", action="store_true", help="Run Bluesky scan only")
    parser.add_argument("--test", action="store_true", help="Test mode (no notifications)")
    parser.add_argument("--digest", action="store_true", help="Send daily digest")

    args = parser.parse_args()

    if args.digest:
        send_daily_digest()
        return

    # If specific platforms selected, run only those
    if any([args.reddit, args.forums, args.hn, args.bluesky]):
        db = LeadDatabase(DATABASE_PATH)
        classifier = LeadClassifier()
        notifier = TelegramNotifier()

        if args.reddit:
            run_reddit_scan(db, classifier, notifier, args.test)
        if args.forums:
            run_forum_scan(db, classifier, notifier, args.test)
        if args.hn:
            run_hackernews_scan(db, classifier, notifier, args.test)
        if args.bluesky:
            run_bluesky_scan(db, classifier, notifier, args.test)
    else:
        # Run full scan
        run_full_scan(test_mode=args.test)


if __name__ == "__main__":
    main()
