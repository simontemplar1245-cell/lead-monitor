"""
ntfy.sh Notification System
=============================
Sends instant push notifications for HOT leads and daily digests.
Uses ntfy.sh - free, no account needed, works over WiFi/data anywhere.

Setup:
  1. Install the ntfy app on your phone (iOS / Android)
  2. Subscribe to your topic (e.g. "advance-ai-leads")
  3. Set NTFY_TOPIC in .env or GitHub Secrets
  4. Done - notifications arrive instantly
"""

import logging
import requests
from datetime import datetime
from typing import Optional

from config import (
    NTFY_TOPIC,
    NTFY_SERVER,
    HOT_ALERT_TEMPLATE,
    WARM_DIGEST_TEMPLATE,
    DAILY_DIGEST_TEMPLATE,
)

logger = logging.getLogger(__name__)


class NtfyNotifier:
    """Sends lead alerts via ntfy.sh push notifications."""

    def __init__(self):
        self.topic = NTFY_TOPIC
        self.server = NTFY_SERVER.rstrip("/")
        self.enabled = bool(self.topic)

        if not self.enabled:
            logger.warning(
                "ntfy.sh notifications disabled - "
                "set NTFY_TOPIC in .env (e.g. NTFY_TOPIC=advance-ai-leads)"
            )

    def send_message(self, text: str, title: str = "Lead Monitor",
                     priority: int = 3, tags: str = "") -> bool:
        """
        Send a push notification via ntfy.sh.

        Priority levels:
          1 = min, 2 = low, 3 = default, 4 = high, 5 = urgent

        Tags are emoji shortcodes, e.g. "fire" shows a fire emoji.
        """
        if not self.enabled:
            logger.info(f"[DRY RUN] Would send ntfy message: {title} - {text[:100]}...")
            return False

        url = f"{self.server}/{self.topic}"

        headers = {
            "Title": title,
            "Priority": str(priority),
        }

        if tags:
            headers["Tags"] = tags

        # Truncate if too long (ntfy has 4096 byte limit for message body)
        if len(text) > 3900:
            text = text[:3897] + "..."

        try:
            response = requests.post(url, data=text.encode("utf-8"), headers=headers, timeout=15)
            response.raise_for_status()
            logger.info(f"ntfy notification sent: {title}")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send ntfy notification: {e}")
            return False

    def send_hot_alert(self, lead_data: dict) -> bool:
        """Send an urgent push notification for a HOT lead."""
        # Calculate time ago
        post_time = lead_data.get("post_created_at", "")
        if post_time:
            try:
                dt = datetime.fromisoformat(str(post_time).replace("Z", "+00:00"))
                diff = datetime.utcnow() - dt.replace(tzinfo=None)
                if diff.total_seconds() < 3600:
                    time_ago = f"{int(diff.total_seconds() / 60)} minutes ago"
                elif diff.total_seconds() < 86400:
                    time_ago = f"{int(diff.total_seconds() / 3600)} hours ago"
                else:
                    time_ago = f"{int(diff.days)} days ago"
            except (ValueError, TypeError):
                time_ago = "Unknown"
        else:
            time_ago = "Just now"

        # Truncate post text
        post_text = lead_data.get("body", lead_data.get("title", ""))
        if len(post_text) > 500:
            post_text = post_text[:497] + "..."

        message = HOT_ALERT_TEMPLATE.format(
            platform=lead_data.get("platform", "Unknown"),
            community=lead_data.get("community", "Unknown"),
            score=f"{lead_data.get('score', 0):.2f}",
            category=lead_data.get("category", "HOT"),
            post_text=post_text,
            post_url=lead_data.get("url", ""),
            suggested_reply=lead_data.get("suggested_reply", ""),
            reasoning=lead_data.get("reasoning", ""),
            time_ago=time_ago,
        )

        logger.info(
            f"Sending HOT alert: {lead_data.get('platform')}/{lead_data.get('community')} "
            f"- score {lead_data.get('score', 0):.2f}"
        )

        return self.send_message(
            text=message,
            title=f"HOT LEAD - {lead_data.get('platform', '')}/{lead_data.get('community', '')}",
            priority=5,  # urgent - makes phone ring/vibrate
            tags="fire",
        )

    def send_warm_alert(self, lead_data: dict) -> bool:
        """Send a notification for a WARM lead (lower priority)."""
        post_text = lead_data.get("body", lead_data.get("title", ""))
        if len(post_text) > 200:
            post_text = post_text[:197] + "..."

        message = WARM_DIGEST_TEMPLATE.format(
            platform=lead_data.get("platform", "Unknown"),
            community=lead_data.get("community", "Unknown"),
            score=f"{lead_data.get('score', 0):.2f}",
            post_text_short=post_text,
            post_url=lead_data.get("url", ""),
            suggested_reply=lead_data.get("suggested_reply", ""),
        )

        return self.send_message(
            text=message,
            title=f"Warm Lead - {lead_data.get('platform', '')}/{lead_data.get('community', '')}",
            priority=3,  # default priority
            tags="zap",
        )

    def send_daily_digest(self, stats: dict, top_sources: list) -> bool:
        """Send the daily summary digest."""
        sources_text = ""
        for src in top_sources[:5]:
            sources_text += f"  {src['community']}: {src['total']} leads ({src.get('hot', 0)} hot)\n"

        if not sources_text:
            sources_text = "  No leads found today"

        message = DAILY_DIGEST_TEMPLATE.format(
            hot_count=stats.get("today_hot", 0),
            warm_count=stats.get("today_warm", 0),
            cold_count=stats.get("cold", 0),
            top_sources=sources_text,
        )

        return self.send_message(
            text=message,
            title="Daily Lead Digest",
            priority=3,
            tags="chart_with_upwards_trend",
        )

    def send_scan_summary(self, all_stats: dict, duration: float) -> bool:
        """
        Send a summary notification after every scan cycle, even if nothing
        was found. Uses low priority so it doesn't spam/ring, but you still
        know the system is alive and working.
        """
        total_scanned = sum(s.get("scanned", 0) for s in all_stats.values())
        total_hot = sum(s.get("hot", 0) for s in all_stats.values())
        total_warm = sum(s.get("warm", 0) for s in all_stats.values())
        total_cold = sum(s.get("cold", 0) for s in all_stats.values())

        # If HOT or WARM leads were already alerted individually, skip the summary
        # to avoid notification spam. Only send summary when nothing actionable found.
        if total_hot > 0 or total_warm > 0:
            return False

        # Nothing found - send a quiet "still alive" heartbeat
        per_platform = []
        for platform_name, stats in all_stats.items():
            scanned = stats.get("scanned", 0)
            if scanned > 0:
                per_platform.append(f"  {platform_name}: {scanned} scanned")

        per_platform_text = "\n".join(per_platform) if per_platform else "  (all sources)"

        message = (
            f"No leads found this scan\n\n"
            f"Scanned: {total_scanned} posts\n"
            f"Filtered cold: {total_cold}\n"
            f"Duration: {duration:.0f}s\n\n"
            f"Sources:\n{per_platform_text}\n\n"
            f"System is running. Next scan in ~30 minutes."
        )

        return self.send_message(
            text=message,
            title="Lead Monitor - Scan Complete (no leads)",
            priority=2,  # low priority - arrives silently, no sound/vibration
            tags="mag",  # magnifying glass emoji
        )

    def send_error_alert(self, error_message: str) -> bool:
        """Send an alert when something goes wrong with the system."""
        message = f"Error: {error_message}\n\nCheck the dashboard for details."

        return self.send_message(
            text=message,
            title="Lead Monitor - System Error",
            priority=4,  # high priority for errors
            tags="warning",
        )
