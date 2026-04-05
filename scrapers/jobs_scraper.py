"""
Jobs Scraper (JobSpy)
=====================
Scrapes Indeed, ZipRecruiter, LinkedIn, and Glassdoor for receptionist
and front desk job postings - the STRONGEST possible buying signal for
an AI receptionist service.

A business actively trying to hire a receptionist has already decided
they need reception coverage. They just don't know yet that an AI can do
the job for ~10% of the cost. Every posting we find = a business we can
cold-pitch with a genuinely relevant solution.

Uses: https://github.com/Bunsly/JobSpy (MIT licensed, no API keys).
"""

import logging
import hashlib
from datetime import datetime, timezone
from typing import Generator

from config import JOBS

logger = logging.getLogger(__name__)


class JobsScraper:
    """Scrapes job boards for receptionist/front desk postings via JobSpy."""

    def __init__(self):
        self.enabled = JOBS.get("enabled", True)
        self.sites = JOBS.get("sites", ["indeed", "zip_recruiter"])
        self.search_terms = JOBS.get("search_terms", ["receptionist"])
        self.locations = JOBS.get("locations", ["United States"])
        self.hours_old = JOBS.get("hours_old", 48)
        self.results_per_search = JOBS.get("results_per_search", 20)
        self.exclude_titles = [t.lower() for t in JOBS.get("exclude_titles", [])]

        # Lazy-import jobspy so the rest of the system still works if the
        # package isn't installed (e.g., during minimal CI runs).
        self._jobspy = None
        try:
            from jobspy import scrape_jobs
            self._jobspy = scrape_jobs
        except ImportError:
            logger.warning(
                "python-jobspy not installed - jobs scraper disabled. "
                "Install with: pip install python-jobspy"
            )
            self.enabled = False

    def scan(self) -> Generator[dict, None, None]:
        """
        Run all searches across all locations and yield job postings as
        lead-shaped dicts for the classifier/notifier pipeline.
        """
        if not self.enabled or self._jobspy is None:
            logger.info("Jobs scraper disabled (package missing or config off)")
            return

        seen_ids = set()

        for search_term in self.search_terms:
            for location in self.locations:
                try:
                    yield from self._search(search_term, location, seen_ids)
                except Exception as e:
                    logger.error(
                        f"JobSpy error for '{search_term}' in {location}: {e}"
                    )

    def _search(self, search_term: str, location: str,
                seen_ids: set) -> Generator[dict, None, None]:
        """Run one JobSpy call and yield normalized lead dicts."""
        logger.info(
            f"JobSpy searching: '{search_term}' in {location} "
            f"(last {self.hours_old}h)"
        )

        try:
            df = self._jobspy(
                site_name=self.sites,
                search_term=search_term,
                location=location,
                results_wanted=self.results_per_search,
                hours_old=self.hours_old,
                country_indeed=self._country_for_indeed(location),
                verbose=0,
            )
        except Exception as e:
            logger.error(f"JobSpy scrape failed: {e}")
            return

        if df is None or len(df) == 0:
            logger.info(f"JobSpy: 0 results for '{search_term}' in {location}")
            return

        logger.info(f"JobSpy: {len(df)} results for '{search_term}' in {location}")

        for _, row in df.iterrows():
            try:
                title = str(row.get("title", "") or "").strip()
                company = str(row.get("company", "") or "").strip()
                description = str(row.get("description", "") or "").strip()
                job_url = str(row.get("job_url", "") or "").strip()
                site = str(row.get("site", "") or "").strip()
                location_str = str(row.get("location", "") or "").strip()
                date_posted = row.get("date_posted", "")

                if not title or not company:
                    continue

                # Filter out senior/management roles - we want solo operators
                # and SMB owners who would cold-buy an AI receptionist
                title_lower = title.lower()
                if any(bad in title_lower for bad in self.exclude_titles):
                    continue

                # Build a stable unique ID for dedup
                unique_key = f"job_{site}_{company}_{title}_{location_str}"
                post_id = f"jobs_{hashlib.md5(unique_key.encode()).hexdigest()[:16]}"
                if post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                # Build the classifier input - include title, company, and
                # enough of the description to matter, but not so much that
                # we blow Haiku's context budget
                desc_snippet = description[:800] if description else ""
                full_text = (
                    f"Job Posting: {title}\n"
                    f"Company: {company}\n"
                    f"Location: {location_str}\n"
                    f"Source: {site}\n\n"
                    f"{desc_snippet}"
                )

                # Normalize date_posted into an ISO string if possible
                post_created_at = ""
                if date_posted:
                    try:
                        if hasattr(date_posted, "isoformat"):
                            post_created_at = date_posted.isoformat()
                        else:
                            post_created_at = str(date_posted)
                    except Exception:
                        post_created_at = str(date_posted)

                yield {
                    "post_id": post_id,
                    "platform": "jobs",
                    "community": f"{site} ({location})",
                    "author": company,
                    "title": title,
                    "body": desc_snippet,
                    "full_text": full_text,
                    "url": job_url,
                    "post_created_at": post_created_at,
                    "post_score": 0,
                    "num_comments": 0,
                    "type": "job_posting",
                    # These fields get merged into the classification so the
                    # Haiku classifier can see them directly and score
                    # hiring posts as WARM/HOT automatically.
                    "keyword_matched": "hiring_signal_job_posting",
                    "keyword_category": "hiring_signals",
                }

            except Exception as e:
                logger.error(f"Error parsing JobSpy row: {e}")
                continue

    @staticmethod
    def _country_for_indeed(location: str) -> str:
        """Map our location strings to Indeed's country codes."""
        loc_lower = location.lower()
        if "canada" in loc_lower:
            return "canada"
        if "united kingdom" in loc_lower or "uk" in loc_lower:
            return "uk"
        if "australia" in loc_lower:
            return "australia"
        return "usa"
