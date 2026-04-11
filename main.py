"""
Lead Monitor - Main Entry Point
================================
Orchestrates the full scanning pipeline:
1. Run all scrapers (Reddit, forums, HN, Bluesky, Jobs)
2. Pre-filter with keywords
3. Classify with Claude Haiku
4. Save to database
5. Buffer all leads, then send ONE ntfy.sh digest notification

Usage:
  python main.py              # Run a full scan cycle
  python main.py --reddit     # Reddit only
  python main.py --forums     # Forums only
  python main.py --hn         # Hacker News only
  python main.py --bluesky    # Bluesky only
  python main.py --jobs       # Job boards only (hiring signals)
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
from core.notifier import NtfyNotifier

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


# =============================================================================
# SHARED LEAD-PROCESSING LOGIC
# =============================================================================

def _process_lead(post_data: dict, db: LeadDatabase,
                  classifier: LeadClassifier, notifier: NtfyNotifier,
                  stats: dict, test_mode: bool,
                  force_warm_floor: bool = False):
    """
    Classify, save, and buffer a single lead.
    Shared by all scan functions to avoid code duplication.

    force_warm_floor: if True, auto-promote COLD→WARM (used for job postings
                      which are inherently buying signals even without pain
                      language).
    """
    if db.is_duplicate(post_data["post_id"]):
        return

    text = post_data.get("full_text", "")
    classification = classifier.classify(
        text,
        platform=post_data.get("platform", ""),
        community=post_data.get("community", ""),
    )

    # For job postings, floor at WARM: a company hiring a receptionist IS
    # a buying signal even if the classifier sees no "complaint" language.
    if force_warm_floor and classification["category"] == "COLD":
        classification["category"] = "WARM"
        classification["score"] = max(
            float(classification.get("score", 0.0)), 0.55
        )
        classification["reasoning"] = (
            f"Hiring signal (auto-promoted): "
            f"{classification.get('reasoning', '')}"
        )

    # Skip cold leads that didn't even match a keyword
    if classification["category"] == "COLD" and not classification.get("keyword_matched"):
        return

    lead_data = {**post_data, **classification}

    lead_id = db.save_lead(lead_data)
    if lead_id is None:
        return

    stats["found"] += 1

    if classification["category"] == "HOT":
        stats["hot"] += 1
    elif classification["category"] == "WARM":
        stats["warm"] += 1
    else:
        stats["cold"] += 1

    # Buffer the lead — ONE digest notification sent at end of scan
    if not test_mode:
        notifier.buffer_lead(lead_data)


# =============================================================================
# SCAN FUNCTIONS
# =============================================================================

def run_reddit_scan(db: LeadDatabase, classifier: LeadClassifier,
                    notifier: NtfyNotifier, test_mode: bool = False) -> dict:
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
            _process_lead(post_data, db, classifier, notifier, stats, test_mode)

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
                   notifier: NtfyNotifier, test_mode: bool = False) -> dict:
    """Run forum scrapers (Dentaltown, ContractorTalk, etc.)."""
    from scrapers.forum_scraper import ForumScraper

    stats = {"scanned": 0, "found": 0, "hot": 0, "warm": 0, "cold": 0, "errors": ""}
    start_time = time.time()

    try:
        scraper = ForumScraper()
        for post_data in scraper.scan_all_forums():
            stats["scanned"] += 1
            _process_lead(post_data, db, classifier, notifier, stats, test_mode)

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
                        notifier: NtfyNotifier, test_mode: bool = False) -> dict:
    """Run Hacker News scraper."""
    from scrapers.hackernews_scraper import HackerNewsScraper

    stats = {"scanned": 0, "found": 0, "hot": 0, "warm": 0, "cold": 0, "errors": ""}
    start_time = time.time()

    try:
        scraper = HackerNewsScraper()
        for post_data in scraper.scan():
            stats["scanned"] += 1
            _process_lead(post_data, db, classifier, notifier, stats, test_mode)

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
                     notifier: NtfyNotifier, test_mode: bool = False) -> dict:
    """Run Bluesky scraper."""
    from scrapers.bluesky_scraper import BlueskyScraper

    stats = {"scanned": 0, "found": 0, "hot": 0, "warm": 0, "cold": 0, "errors": ""}
    start_time = time.time()

    try:
        scraper = BlueskyScraper()
        for post_data in scraper.scan():
            stats["scanned"] += 1
            _process_lead(post_data, db, classifier, notifier, stats, test_mode)

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


def run_reddit_search_scan(db: LeadDatabase, classifier: LeadClassifier,
                           notifier: NtfyNotifier,
                           test_mode: bool = False) -> dict:
    """
    Search ALL of Reddit for high-intent buyer queries.
    Unlike run_reddit_scan (which monitors specific subreddits), this uses
    reddit.com/search to find people anywhere on Reddit who are actively
    looking to buy a chatbot or virtual receptionist.
    """
    from scrapers.reddit_search_scraper import RedditSearchScraper

    stats = {"scanned": 0, "found": 0, "hot": 0, "warm": 0, "cold": 0, "errors": ""}
    start_time = time.time()

    try:
        scraper = RedditSearchScraper()
        if not scraper.enabled:
            stats["errors"] = "Reddit search scraper disabled"
            return stats

        for post_data in scraper.scan():
            stats["scanned"] += 1
            _process_lead(post_data, db, classifier, notifier, stats, test_mode)

    except Exception as e:
        stats["errors"] = str(e)
        logger.error(f"Reddit search scan error: {e}", exc_info=True)

    duration = time.time() - start_time
    db.log_scan("reddit_search", "all", stats["scanned"], stats["found"],
                stats["hot"], stats["warm"], stats["cold"],
                stats["errors"], duration)

    logger.info(
        f"Reddit search complete: {stats['scanned']} scanned, "
        f"{stats['found']} leads ({stats['hot']} hot, {stats['warm']} warm) "
        f"in {duration:.1f}s"
    )
    return stats


def run_jobs_scan(db: LeadDatabase, classifier: LeadClassifier,
                  notifier: NtfyNotifier, test_mode: bool = False) -> dict:
    """
    Run the jobs scraper (JobSpy - Indeed / LinkedIn).

    Every result is a receptionist / phone role at a real company. These are
    inherently buying signals so we force-floor them at WARM even when the
    classifier scores them COLD (job descriptions don't contain traditional
    pain language).
    """
    from scrapers.jobs_scraper import JobsScraper

    stats = {"scanned": 0, "found": 0, "hot": 0, "warm": 0, "cold": 0, "errors": ""}
    start_time = time.time()

    try:
        scraper = JobsScraper()
        if not scraper.enabled:
            stats["errors"] = "Jobs scraper not configured (python-jobspy missing)"
            return stats

        for post_data in scraper.scan():
            stats["scanned"] += 1
            _process_lead(
                post_data, db, classifier, notifier, stats, test_mode,
                force_warm_floor=True,  # Job posting = buying signal
            )

    except Exception as e:
        stats["errors"] = str(e)
        logger.error(f"Jobs scan error: {e}", exc_info=True)

    duration = time.time() - start_time
    db.log_scan("jobs", "Job Boards", stats["scanned"], stats["found"],
                stats["hot"], stats["warm"], stats["cold"],
                stats["errors"], duration)

    logger.info(
        f"Jobs scan complete: {stats['scanned']} scanned, "
        f"{stats['found']} leads ({stats['hot']} hot, {stats['warm']} warm) "
        f"in {duration:.1f}s"
    )
    return stats


def run_complaint_scan(db: LeadDatabase, classifier: LeadClassifier,
                        notifier: NtfyNotifier,
                        test_mode: bool = False) -> dict:
    """
    Scrape review sites (Yelp / BBB / Trustpilot / Google Maps) via DDG
    for 1-star complaints explicitly about phone unreachability and
    missed calls. This is the highest-intent lead source we have: every
    match is a business with a PUBLIC customer complaint about the exact
    problem our AI receptionist fixes.
    """
    from scrapers.complaint_scraper import ComplaintScraper

    stats = {"scanned": 0, "found": 0, "hot": 0, "warm": 0, "cold": 0, "errors": ""}
    start_time = time.time()

    try:
        scraper = ComplaintScraper()
        if not scraper.enabled:
            stats["errors"] = "Complaint scraper disabled"
            return stats

        for post_data in scraper.scan_all():
            stats["scanned"] += 1
            # Complaints are inherently buying signals — force WARM floor
            # so the classifier doesn't drop them for lack of "pain" words
            # in the short snippet.
            _process_lead(
                post_data, db, classifier, notifier, stats, test_mode,
                force_warm_floor=True,
            )

    except Exception as e:
        stats["errors"] = str(e)
        logger.error(f"Complaint scan error: {e}", exc_info=True)

    duration = time.time() - start_time
    db.log_scan("complaints", "review sites", stats["scanned"], stats["found"],
                stats["hot"], stats["warm"], stats["cold"],
                stats["errors"], duration)

    logger.info(
        f"Complaint scan complete: {stats['scanned']} scanned, "
        f"{stats['found']} leads ({stats['hot']} hot, {stats['warm']} warm) "
        f"in {duration:.1f}s"
    )
    return stats


def run_craigslist_scan(db: LeadDatabase, classifier: LeadClassifier,
                         notifier: NtfyNotifier,
                         test_mode: bool = False) -> dict:
    """Scrape Craigslist small-biz / services RSS feeds across target cities."""
    from scrapers.craigslist_scraper import CraigslistScraper

    stats = {"scanned": 0, "found": 0, "hot": 0, "warm": 0, "cold": 0, "errors": ""}
    start_time = time.time()

    try:
        scraper = CraigslistScraper()
        if not scraper.enabled:
            stats["errors"] = "Craigslist scraper disabled"
            return stats

        for post_data in scraper.scan_all():
            stats["scanned"] += 1
            _process_lead(post_data, db, classifier, notifier, stats, test_mode)

    except Exception as e:
        stats["errors"] = str(e)
        logger.error(f"Craigslist scan error: {e}", exc_info=True)

    duration = time.time() - start_time
    db.log_scan("craigslist", "all cities", stats["scanned"], stats["found"],
                stats["hot"], stats["warm"], stats["cold"],
                stats["errors"], duration)

    logger.info(
        f"Craigslist scan complete: {stats['scanned']} scanned, "
        f"{stats['found']} leads ({stats['hot']} hot, {stats['warm']} warm) "
        f"in {duration:.1f}s"
    )
    return stats


def run_quora_scan(db: LeadDatabase, classifier: LeadClassifier,
                    notifier: NtfyNotifier,
                    test_mode: bool = False) -> dict:
    """Find Quora questions matching buying-intent queries via DDG."""
    from scrapers.quora_scraper import QuoraScraper

    stats = {"scanned": 0, "found": 0, "hot": 0, "warm": 0, "cold": 0, "errors": ""}
    start_time = time.time()

    try:
        scraper = QuoraScraper()
        if not scraper.enabled:
            stats["errors"] = "Quora scraper disabled"
            return stats

        for post_data in scraper.scan_all():
            stats["scanned"] += 1
            # Quora questions with buying intent phrasing are warm by default
            _process_lead(
                post_data, db, classifier, notifier, stats, test_mode,
                force_warm_floor=True,
            )

    except Exception as e:
        stats["errors"] = str(e)
        logger.error(f"Quora scan error: {e}", exc_info=True)

    duration = time.time() - start_time
    db.log_scan("quora", "quora", stats["scanned"], stats["found"],
                stats["hot"], stats["warm"], stats["cold"],
                stats["errors"], duration)

    logger.info(
        f"Quora scan complete: {stats['scanned']} scanned, "
        f"{stats['found']} leads ({stats['hot']} hot, {stats['warm']} warm) "
        f"in {duration:.1f}s"
    )
    return stats


# =============================================================================
# FULL SCAN ORCHESTRATOR
# =============================================================================

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
    notifier = NtfyNotifier()

    # Run all scrapers — leads are BUFFERED in notifier, not sent yet
    all_stats = {}

    logger.info("--- Reddit Scan ---")
    all_stats["reddit"] = run_reddit_scan(db, classifier, notifier, test_mode)

    logger.info("--- Forum Scan ---")
    all_stats["forums"] = run_forum_scan(db, classifier, notifier, test_mode)

    logger.info("--- Hacker News Scan ---")
    all_stats["hackernews"] = run_hackernews_scan(db, classifier, notifier, test_mode)

    logger.info("--- Bluesky Scan ---")
    all_stats["bluesky"] = run_bluesky_scan(db, classifier, notifier, test_mode)

    logger.info("--- Reddit Search (high-intent buyer queries) ---")
    all_stats["reddit_search"] = run_reddit_search_scan(
        db, classifier, notifier, test_mode
    )

    logger.info("--- Jobs Scan (hiring signals) ---")
    all_stats["jobs"] = run_jobs_scan(db, classifier, notifier, test_mode)

    logger.info("--- Complaint Scan (Yelp/BBB/Trustpilot review complaints) ---")
    all_stats["complaints"] = run_complaint_scan(db, classifier, notifier, test_mode)

    logger.info("--- Craigslist Scan (small biz / services RSS) ---")
    all_stats["craigslist"] = run_craigslist_scan(db, classifier, notifier, test_mode)

    logger.info("--- Quora Scan (buying-intent questions) ---")
    all_stats["quora"] = run_quora_scan(db, classifier, notifier, test_mode)

    # =========================================================================
    # ENRICH HOT/WARM leads with contact info (email/phone/website)
    # =========================================================================
    try:
        from core.enricher import enrich_pending_leads
        logger.info("--- Enriching leads with contact info ---")
        enrich_pending_leads(db, limit=30)
    except Exception as e:
        logger.warning(f"Enrichment skipped due to error: {e}")

    # =========================================================================
    # SEND ONE DIGEST NOTIFICATION with all buffered leads
    # =========================================================================
    if not test_mode:
        logger.info("--- Sending Digest ---")
        notifier.flush_digest()

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
        notifier.send_error_alert(
            f"Scan completed with errors: {'; '.join(total_errors)}"
        )

    # Quiet heartbeat if nothing was found (digest already handled leads)
    if not test_mode:
        notifier.send_scan_summary(all_stats, total_time)

    return all_stats


def send_daily_digest():
    """Send the daily summary digest via ntfy.sh."""
    db = LeadDatabase(DATABASE_PATH)
    notifier = NtfyNotifier()

    stats = db.get_stats_summary(days=1)
    sources = db.get_platform_stats(days=1)

    notifier.send_daily_digest(stats, sources)
    logger.info("Daily digest sent")


def main():
    parser = argparse.ArgumentParser(
        description="Lead Monitor for Advance AI Services"
    )
    parser.add_argument("--reddit", action="store_true", help="Run Reddit scan only")
    parser.add_argument("--forums", action="store_true", help="Run forum scan only")
    parser.add_argument("--hn", action="store_true", help="Run Hacker News scan only")
    parser.add_argument("--bluesky", action="store_true", help="Run Bluesky scan only")
    parser.add_argument("--reddit-search", action="store_true",
                        help="Run Reddit cross-search only (high-intent queries)")
    parser.add_argument("--jobs", action="store_true",
                        help="Run jobs scan only (hiring signals)")
    parser.add_argument("--complaints", action="store_true",
                        help="Run complaint scan only (Yelp/BBB/Trustpilot)")
    parser.add_argument("--craigslist", action="store_true",
                        help="Run Craigslist scan only")
    parser.add_argument("--quora", action="store_true",
                        help="Run Quora scan only")
    parser.add_argument("--test", action="store_true",
                        help="Test mode (no notifications)")
    parser.add_argument("--digest", action="store_true", help="Send daily digest")

    args = parser.parse_args()

    if args.digest:
        send_daily_digest()
        return

    # If specific platforms selected, run only those
    if any([args.reddit, args.forums, args.hn, args.bluesky,
            args.reddit_search, args.jobs, args.complaints,
            args.craigslist, args.quora]):
        db = LeadDatabase(DATABASE_PATH)
        classifier = LeadClassifier()
        notifier = NtfyNotifier()

        if args.reddit:
            run_reddit_scan(db, classifier, notifier, args.test)
        if args.forums:
            run_forum_scan(db, classifier, notifier, args.test)
        if args.hn:
            run_hackernews_scan(db, classifier, notifier, args.test)
        if args.bluesky:
            run_bluesky_scan(db, classifier, notifier, args.test)
        if args.reddit_search:
            run_reddit_search_scan(db, classifier, notifier, args.test)
        if args.jobs:
            run_jobs_scan(db, classifier, notifier, args.test)
        if args.complaints:
            run_complaint_scan(db, classifier, notifier, args.test)
        if args.craigslist:
            run_craigslist_scan(db, classifier, notifier, args.test)
        if args.quora:
            run_quora_scan(db, classifier, notifier, args.test)

        # Flush any buffered leads as ONE notification
        if not args.test:
            notifier.flush_digest()
    else:
        # Run full scan (flush is called inside run_full_scan)
        run_full_scan(test_mode=args.test)


if __name__ == "__main__":
    main()
