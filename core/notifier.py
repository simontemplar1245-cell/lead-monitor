"""
Telegram Notification System
=============================
Sends instant alerts for HOT leads and daily digests for WARM leads.
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    HOT_ALERT_TEMPLATE,
    WARM_DIGEST_TEMPLATE,
    DAILY_DIGEST_TEMPLATE,
)

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends lead alerts via Telegram bot."""

    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(self.bot_token and self.chat_id)

        if not self.enabled:
            logger.warning(
                "Telegram notifications disabled - "
                "set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
            )

    async def _send_message_async(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a message via Telegram Bot API using python-telegram-bot."""
        if not self.enabled:
            logger.info(f"[DRY RUN] Would send Telegram message: {text[:100]}...")
            return False

        try:
            from telegram import Bot

            bot = Bot(token=self.bot_token)
            # Truncate if too long for Telegram (max 4096 chars)
            if len(text) > 4000:
                text = text[:3997] + "..."

            await bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=True,
            )
            logger.info("Telegram message sent successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            # Try without markdown formatting if it failed
            try:
                await bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    disable_web_page_preview=True,
                )
                return True
            except Exception as e2:
                logger.error(f"Telegram retry also failed: {e2}")
                return False

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Synchronous wrapper for sending messages."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in an async context, create a task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._send_message_async(text, parse_mode)
                    )
                    return future.result(timeout=30)
            else:
                return asyncio.run(self._send_message_async(text, parse_mode))
        except Exception as e:
            logger.error(f"Send message error: {e}")
            return False

    def send_hot_alert(self, lead_data: dict) -> bool:
        """Send an instant alert for a HOT lead."""
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

        # Truncate post text for Telegram
        post_text = lead_data.get("body", lead_data.get("title", ""))
        if len(post_text) > 500:
            post_text = post_text[:497] + "..."

        # Escape markdown special chars in user content
        post_text = self._escape_markdown(post_text)
        suggested = self._escape_markdown(lead_data.get("suggested_reply", ""))
        reasoning = self._escape_markdown(lead_data.get("reasoning", ""))

        message = HOT_ALERT_TEMPLATE.format(
            platform=lead_data.get("platform", "Unknown"),
            community=lead_data.get("community", "Unknown"),
            score=f"{lead_data.get('score', 0):.2f}",
            category=lead_data.get("category", "HOT"),
            post_text=post_text,
            post_url=lead_data.get("url", ""),
            suggested_reply=suggested,
            reasoning=reasoning,
            time_ago=time_ago,
        )

        logger.info(
            f"Sending HOT alert: {lead_data.get('platform')}/{lead_data.get('community')} "
            f"- score {lead_data.get('score', 0):.2f}"
        )
        return self.send_message(message)

    def send_warm_alert(self, lead_data: dict) -> bool:
        """Send alert for a WARM lead (less urgent formatting)."""
        post_text = lead_data.get("body", lead_data.get("title", ""))
        if len(post_text) > 200:
            post_text = post_text[:197] + "..."

        post_text = self._escape_markdown(post_text)
        suggested = self._escape_markdown(lead_data.get("suggested_reply", ""))

        message = WARM_DIGEST_TEMPLATE.format(
            platform=lead_data.get("platform", "Unknown"),
            community=lead_data.get("community", "Unknown"),
            score=f"{lead_data.get('score', 0):.2f}",
            post_text_short=post_text,
            post_url=lead_data.get("url", ""),
            suggested_reply=suggested,
        )

        return self.send_message(message)

    def send_daily_digest(self, stats: dict, top_sources: list) -> bool:
        """Send a daily summary digest."""
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

        return self.send_message(message)

    def send_error_alert(self, error_message: str) -> bool:
        """Send an alert when something goes wrong with the system."""
        message = (
            f"System Alert\n\n"
            f"Error: {self._escape_markdown(error_message)}\n\n"
            f"Check the dashboard for details."
        )
        return self.send_message(message)

    @staticmethod
    def _escape_markdown(text: str) -> str:
        """Escape Markdown special characters for Telegram."""
        if not text:
            return ""
        # Only escape characters that break Telegram Markdown v1
        for char in ['_', '*', '[', ']', '`']:
            text = text.replace(char, f'\\{char}')
        return text
