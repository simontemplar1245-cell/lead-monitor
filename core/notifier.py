"""
ntfy.sh Notification System
=============================
Sends ONE digest notification per scan cycle with ALL leads bundled.
No more individual alerts — every scan produces at most one notification.

If a scan finds many leads, the notification body contains the top leads
and a downloadable .txt report is attached with full details on every lead.

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
    DAILY_DIGEST_TEMPLATE,
)

logger = logging.getLogger(__name__)

# Max leads to show inline in the notification body (ntfy 4096 byte limit)
MAX_INLINE_LEADS = 10


class NtfyNotifier:
    """Sends lead alerts via ntfy.sh push notifications."""

    def __init__(self):
        self.topic = NTFY_TOPIC
        self.server = NTFY_SERVER.rstrip("/")
        self.enabled = bool(self.topic)
        # Buffer: collect leads during a scan, send ONE digest at the end
        self._lead_buffer = []

        if not self.enabled:
            logger.warning(
                "ntfy.sh notifications disabled - "
                "set NTFY_TOPIC in .env (e.g. NTFY_TOPIC=advance-ai-leads)"
            )

    # =========================================================================
    # PUBLIC API — called from main.py scan loops
    # =========================================================================

    def buffer_lead(self, lead_data: dict):
        """
        Buffer a lead for the end-of-scan digest.
        Called instead of the old send_hot_alert / send_warm_alert.
        """
        self._lead_buffer.append(lead_data)
        category = lead_data.get("category", "?")
        company, title = self._extract_company_and_title(lead_data)
        logger.info(f"Buffered [{category}] lead: {company} — {title[:60]}")

    def flush_digest(self) -> bool:
        """
        Send all buffered leads as ONE notification.
        If >MAX_INLINE_LEADS, attaches a full .txt report.
        Call this ONCE at the end of run_full_scan().
        """
        if not self._lead_buffer:
            logger.info("No leads to send in digest (buffer empty)")
            return False

        # Sort: HOT first (desc score), then WARM
        leads = sorted(
            self._lead_buffer,
            key=lambda x: (-1 if x.get("category") == "HOT" else 0,
                           -float(x.get("score", 0))),
        )

        hot = [l for l in leads if l.get("category") == "HOT"]
        warm = [l for l in leads if l.get("category") == "WARM"]
        total = len(leads)

        # --- Build the notification body (compact, inline) ---
        title = f"Lead Report: {len(hot)} HOT, {len(warm)} WARM ({total} total)"
        dashboard_url = "https://simontemplar1245-cell.github.io/lead-monitor/"
        body_lines = [f"Found {total} leads this scan.\nDashboard: {dashboard_url}\n"]

        for i, lead in enumerate(leads[:MAX_INLINE_LEADS]):
            body_lines.append(self._format_lead_compact(lead, i + 1))

        if total > MAX_INLINE_LEADS:
            body_lines.append(
                f"\n... and {total - MAX_INLINE_LEADS} more."
                f"\nTap to download the full report."
            )

        body = "\n".join(body_lines)

        # --- Decide delivery method ---
        priority = 5 if hot else 3
        tags = "fire" if hot else "zap"
        click_url = "https://simontemplar1245-cell.github.io/lead-monitor/"

        if total > MAX_INLINE_LEADS:
            # Many leads → attach a full report file
            report = self._build_full_report(leads, hot, warm)
            result = self._send_with_attachment(
                filename=f"leads-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.txt",
                file_content=report,
                title=title,
                message=body[:1024],  # ntfy Message header limit
                priority=priority,
                tags=tags,
                click_url=click_url,
            )
        else:
            # Few leads → all fit in one notification body
            result = self.send_message(
                text=body,
                title=title,
                priority=priority,
                tags=tags,
                click_url=click_url,
            )

        logger.info(
            f"Digest sent: {len(hot)} HOT, {len(warm)} WARM, "
            f"{total} total leads (result={result})"
        )
        self._lead_buffer.clear()
        return result

    # =========================================================================
    # LOW-LEVEL SENDING
    # =========================================================================

    def send_message(self, text: str, title: str = "Lead Monitor",
                     priority: int = 3, tags: str = "",
                     click_url: str = "") -> bool:
        """Send a plain-text push notification via ntfy.sh."""
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
        if click_url:
            headers["Click"] = click_url

        # Truncate if too long (ntfy has 4096 byte limit for message body)
        if len(text) > 3900:
            text = text[:3897] + "..."

        try:
            response = requests.post(
                url, data=text.encode("utf-8"), headers=headers, timeout=15
            )
            response.raise_for_status()
            logger.info(f"ntfy notification sent: {title}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send ntfy notification: {e}")
            return False

    def _send_with_attachment(self, filename: str, file_content: str,
                              title: str, message: str,
                              priority: int = 3, tags: str = "",
                              click_url: str = "") -> bool:
        """
        Send a notification with a downloadable file attachment.
        ntfy.sh hosts the file temporarily (~12 hours on the free tier).
        The notification shows the title + message, with a 'Download' button.
        """
        if not self.enabled:
            logger.info(
                f"[DRY RUN] Would send ntfy digest with attachment: "
                f"{title} ({filename}, {len(file_content)} bytes)"
            )
            return False

        url = f"{self.server}/{self.topic}"
        headers = {
            "Filename": filename,
            "Title": title,
            "Message": message,
            "Priority": str(priority),
        }
        if tags:
            headers["Tags"] = tags
        if click_url:
            headers["Click"] = click_url

        try:
            response = requests.put(
                url,
                data=file_content.encode("utf-8"),
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            logger.info(f"ntfy digest sent with attachment: {filename}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send ntfy digest with attachment: {e}")
            # Fallback: send truncated body without attachment
            return self.send_message(
                text=message[:3900],
                title=title,
                priority=priority,
                tags=tags,
            )

    # =========================================================================
    # FORMATTING HELPERS
    # =========================================================================

    def _format_lead_compact(self, lead: dict, number: int) -> str:
        """Format one lead as a compact 4-line block for the notification body."""
        company, title = self._extract_company_and_title(lead)
        time_ago = self._format_time_ago(lead.get("post_created_at", ""))
        platform = lead.get("platform", "")
        community = lead.get("community", "")
        category = lead.get("category", "")

        icon = "🔥" if category == "HOT" else "⚡"

        if platform == "jobs":
            return (
                f"{'━' * 30}\n"
                f"{icon} #{number} {category} — {company}\n"
                f"   Role: {title[:60]}\n"
                f"   {community} | {time_ago}\n"
                f"   🔗 {lead.get('url', 'N/A')}"
            )
        else:
            return (
                f"{'━' * 30}\n"
                f"{icon} #{number} {category} — {community}\n"
                f"   {title[:70]}\n"
                f"   by {company} | {time_ago}\n"
                f"   🔗 {lead.get('url', 'N/A')}"
            )

    def _build_full_report(self, leads: list, hot: list, warm: list) -> str:
        """Build a detailed plain-text report with ALL lead details."""
        lines = [
            "ADVANCE AI SERVICES — LEAD REPORT",
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
            f"Total: {len(leads)} leads ({len(hot)} HOT, {len(warm)} WARM)",
            "",
        ]

        if hot:
            lines.append("=" * 50)
            lines.append(f"🔥  HOT LEADS ({len(hot)})")
            lines.append("=" * 50)
            for i, lead in enumerate(hot, 1):
                lines.append(self._format_lead_detail(lead, i))

        if warm:
            lines.append("")
            lines.append("=" * 50)
            lines.append(f"⚡  WARM LEADS ({len(warm)})")
            lines.append("=" * 50)
            for i, lead in enumerate(warm, 1):
                lines.append(self._format_lead_detail(lead, i))

        lines.append("")
        lines.append("— Advance AI Services Lead Monitor")
        return "\n".join(lines)

    def _format_lead_detail(self, lead: dict, number: int) -> str:
        """Format one lead with FULL detail for the downloadable report."""
        company, title = self._extract_company_and_title(lead)
        time_ago = self._format_time_ago(lead.get("post_created_at", ""))
        platform = lead.get("platform", "")
        community = lead.get("community", "")
        score = lead.get("score", 0)
        reasoning = lead.get("reasoning", "")
        suggested_reply = lead.get("suggested_reply", "")

        post_text = lead.get("body", lead.get("title", ""))
        if len(post_text) > 400:
            post_text = post_text[:397] + "..."

        url = lead.get("url", "N/A")

        if platform == "jobs":
            return (
                f"\n{'-' * 45}\n"
                f"  {number}. {company} — {title}\n"
                f"     Source: {community}\n"
                f"     Posted: {time_ago}\n"
                f"     Score: {score:.2f}\n"
                f"\n"
                f"     Summary:\n"
                f"     {post_text[:300]}\n"
                f"\n"
                f"     Why this is a lead:\n"
                f"     {company} is hiring for a receptionist/phone role.\n"
                f"     That's the exact job your AI receptionist does.\n"
                f"\n"
                f"     Suggested pitch:\n"
                f"     {suggested_reply or 'Reach out with a cost comparison: role salary vs AI monthly plan.'}\n"
                f"\n"
                f"     Link: {url}"
            )
        else:
            return (
                f"\n{'-' * 45}\n"
                f"  {number}. {company} on {community} — {title[:70]}\n"
                f"     Posted: {time_ago}\n"
                f"     Score: {score:.2f}\n"
                f"\n"
                f"     Post:\n"
                f"     {post_text[:300]}\n"
                f"\n"
                f"     Why this is a lead:\n"
                f"     {reasoning}\n"
                f"\n"
                f"     Suggested reply:\n"
                f"     {suggested_reply}\n"
                f"\n"
                f"     Link: {url}"
            )

    # =========================================================================
    # UTILITY HELPERS
    # =========================================================================

    @staticmethod
    def _format_time_ago(post_time: str) -> str:
        """Humanize an ISO timestamp into 'X minutes/hours/days ago'."""
        if not post_time:
            return "Just now"
        try:
            dt = datetime.fromisoformat(str(post_time).replace("Z", "+00:00"))
            diff = datetime.utcnow() - dt.replace(tzinfo=None)
            secs = diff.total_seconds()
            if secs < 60:
                return "just now"
            if secs < 3600:
                return f"{int(secs / 60)} minutes ago"
            if secs < 86400:
                return f"{int(secs / 3600)} hours ago"
            return f"{int(diff.days)} days ago"
        except (ValueError, TypeError):
            return "Unknown"

    @staticmethod
    def _extract_company_and_title(lead_data: dict) -> tuple:
        """
        Extract the 'who' and 'what' from a lead.
        Jobs: author=Company, title=Role.
        Social: author=username, title=post title.
        """
        platform = (lead_data.get("platform") or "").lower()
        author = lead_data.get("author") or ""
        title = lead_data.get("title") or ""

        if platform == "jobs":
            return author or "Unknown company", title or "(no title)"

        company = author or "Unknown poster"
        if not title:
            body = lead_data.get("body") or ""
            title = body[:80] + ("..." if len(body) > 80 else "")
        if not title:
            title = "(no title)"
        return company, title

    # =========================================================================
    # STANDALONE METHODS (daily digest, heartbeat, errors)
    # =========================================================================

    def send_daily_digest(self, stats: dict, top_sources: list) -> bool:
        """Send the daily summary digest."""
        sources_text = ""
        for src in top_sources[:5]:
            sources_text += (
                f"  {src['community']}: {src['total']} leads "
                f"({src.get('hot', 0)} hot)\n"
            )
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
        Quiet heartbeat when a scan finds zero leads.
        Skips itself if the digest already sent leads.
        """
        total_scanned = sum(s.get("scanned", 0) for s in all_stats.values())
        total_hot = sum(s.get("hot", 0) for s in all_stats.values())
        total_warm = sum(s.get("warm", 0) for s in all_stats.values())
        total_cold = sum(s.get("cold", 0) for s in all_stats.values())

        # If the digest already fired (leads found), skip heartbeat
        if total_hot > 0 or total_warm > 0:
            return False

        per_platform = []
        for platform_name, stats in all_stats.items():
            scanned = stats.get("scanned", 0)
            if scanned > 0:
                per_platform.append(f"  {platform_name}: {scanned} scanned")
        per_platform_text = (
            "\n".join(per_platform) if per_platform else "  (all sources)"
        )

        message = (
            f"No leads found this scan\n\n"
            f"Scanned: {total_scanned} posts\n"
            f"Filtered cold: {total_cold}\n"
            f"Duration: {duration:.0f}s\n\n"
            f"Sources:\n{per_platform_text}\n\n"
            f"System is running. Next scan in ~1 hour."
        )
        return self.send_message(
            text=message,
            title="Lead Monitor - Scan Complete (no leads)",
            priority=2,
            tags="mag",
        )

    def send_error_alert(self, error_message: str) -> bool:
        """Send an alert when something goes wrong with the system."""
        message = f"Error: {error_message}\n\nCheck the dashboard for details."
        return self.send_message(
            text=message,
            title="Lead Monitor - System Error",
            priority=4,
            tags="warning",
        )
