import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from html import escape
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


class Notifier:
    """Handles admin notifications for monitoring the Telegram Summarizer Bot."""
    
    def __init__(self, bot: Bot, admin_chat_id: Optional[str] = None):
        self.bot = bot
        self.admin_chat_id = admin_chat_id or os.getenv("ADMIN_CHAT_ID")
        
        if not self.admin_chat_id:
            logger.warning("ADMIN_CHAT_ID not set - monitoring notifications disabled")
    
    async def _send_notification(self, message: str, parse_mode: str = 'HTML') -> bool:
        """Send a notification message to the admin chat."""
        if not self.admin_chat_id:
            logger.debug("Admin chat ID not configured - skipping notification")
            return False
            
        try:
            await self.bot.send_message(
                chat_id=self.admin_chat_id,
                text=message,
                parse_mode=parse_mode
            )
            return True
        except TelegramError as e:
            logger.error(f"Failed to send admin notification: {e}")
            return False
    
    async def notify_bot_blocked(self, username: str, telegram_id: int) -> None:
        """Notify admin when a user blocks the bot."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = (
            f"🚫 <b>Bot Blocked</b>\n\n"
            f"👤 User: @{escape(str(username))}\n"
            f"🆔 Telegram ID: <code>{escape(str(telegram_id))}</code>\n"
            f"❌ Status: Bot has been blocked by user\n"
            f"🕒 Time: {escape(timestamp)}"
        )
        await self._send_notification(message)
    
    async def notify_user_returned(self, username: str, telegram_id: int) -> None:
        """Notify admin when a previously blocked user returns."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = (
            f"✅ <b>User Returned</b>\n\n"
            f"👤 User: @{escape(str(username))}\n"
            f"🆔 Telegram ID: <code>{escape(str(telegram_id))}</code>\n"
            f"🔓 Status: User unblocked the bot\n"
            f"🕒 Time: {escape(timestamp)}"
        )
        await self._send_notification(message)
    
    async def notify_user_inactive(self, username: str, telegram_id: int, days_inactive: int) -> None:
        """Notify admin about inactive users (potential churn)."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = (
            f"😴 <b>Inactive User Alert</b>\n\n"
            f"👤 User: @{escape(str(username))}\n"
            f"🆔 Telegram ID: <code>{escape(str(telegram_id))}</code>\n"
            f"📅 Days Inactive: {escape(str(days_inactive))}\n"
            f"⚠️ Status: Potential churn risk\n"
            f"🕒 Time: {escape(timestamp)}"
        )
        await self._send_notification(message)

    async def notify_new_user(self, username: str, telegram_id: int, user_count: int) -> None:
        """Notify admin about new user registration."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = (
            f"🆕 <b>New User Registered</b>\n\n"
            f"👤 Username: @{escape(str(username))}\n"
            f"🆔 Telegram ID: <code>{escape(str(telegram_id))}</code>\n"
            f"📊 Total Users: {escape(str(user_count))}\n"
            f"🕒 Time: {escape(timestamp)}"
        )
        await self._send_notification(message)
    
    async def notify_user_activity(self, username: str, activity_type: str, details: Dict[str, Any]) -> None:
        """Notify admin about user activity (topics/sources changes)."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if activity_type == "topics_added":
            topics = ", ".join([escape(str(t)) for t in details.get("topics", [])])
            message = (
                f"📝 <b>Topics Added</b>\n\n"
                f"👤 User: @{escape(str(username))}\n"
                f"➕ Added: {topics}\n"
                f"📊 Total Topics: {escape(str(details.get('total_count', 'N/A')))}\n"
                f"🕒 Time: {escape(timestamp)}"
            )
        elif activity_type == "sources_added":
            sources = ", ".join([escape(str(s)) for s in details.get("sources", [])])
            message = (
                f"📡 <b>Sources Added</b>\n\n"
                f"👤 User: @{escape(str(username))}\n"
                f"➕ Added: {sources}\n"
                f"📊 Total Sources: {escape(str(details.get('total_count', 'N/A')))}\n"
                f"🕒 Time: {escape(timestamp)}"
            )
        elif activity_type == "topics_removed":
            message = (
                f"🗑️ <b>Topic Removed</b>\n\n"
                f"👤 User: @{escape(str(username))}\n"
                f"➖ Removed: {escape(str(details.get('topic', 'N/A')))}\n"
                f"📊 Remaining Topics: {escape(str(details.get('total_count', 'N/A')))}\n"
                f"🕒 Time: {escape(timestamp)}"
            )
        elif activity_type == "sources_removed":
            message = (
                f"🗑️ <b>Source Removed</b>\n\n"
                f"👤 User: @{escape(str(username))}\n"
                f"➖ Removed: {escape(str(details.get('source', 'N/A')))}\n"
                f"📊 Remaining Sources: {escape(str(details.get('total_count', 'N/A')))}\n"
                f"🕒 Time: {escape(timestamp)}"
            )
        else:
            message = (
                f"📊 <b>User Activity</b>\n\n"
                f"👤 User: @{escape(str(username))}\n"
                f"🔄 Activity: {escape(str(activity_type))}\n"
                f"📋 Details: {escape(str(details))}\n"
                f"🕒 Time: {escape(timestamp)}"
            )
        
        await self._send_notification(message)
    
    async def notify_system_performance(self, event_type: str, details: Dict[str, Any]) -> None:
        """Notify admin about system performance events."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if event_type == "collection_started":
            message = (
                f"🔄 <b>Collection Started</b>\n\n"
                f"📅 Time: {escape(timestamp)}\n"
                f"🔄 Type: {escape('Initial' if details.get('is_initial') else 'Regular')}"
            )
        elif event_type == "collection_completed":
            duration = details.get('duration', 'N/A')
            messages_collected = details.get('messages_collected', 'N/A')
            messages_processed = details.get('messages_processed')
            skipped_empty = details.get('skipped_empty')
            skipped_old = details.get('skipped_old')
            lines = [
                "✅ <b>Collection Completed</b>\n",
                f"📊 Messages Collected: {escape(str(messages_collected))}",
                f"⏱️ Duration: {escape(str(duration))}s",
            ]
            if messages_processed is not None:
                lines.append(f"🧮 Messages Processed: {escape(str(messages_processed))}")
            if skipped_empty is not None:
                lines.append(f"🚫 Skipped (empty): {escape(str(skipped_empty))}")
            if skipped_old is not None:
                lines.append(f"⏳ Skipped (too old): {escape(str(skipped_old))}")
            lines.append(f"📅 Time: {escape(timestamp)}")
            message = "\n".join(lines)
        elif event_type == "filtering_completed":
            filtered_count = details.get('filtered_messages', 'N/A')
            users_processed = details.get('users_processed')
            topics_matched = details.get('topics_matched')
            duration = details.get('duration', 'N/A')
            lines = [
                "🎯 <b>Filtering Completed</b>\n",
                f"📊 Messages Filtered: {escape(str(filtered_count))}",
                f"⏱️ Duration: {escape(str(duration))}s",
            ]
            if users_processed is not None:
                lines.append(f"👥 Users Processed: {escape(str(users_processed))}")
            if topics_matched is not None:
                lines.append(f"🏷️ Topics Matched: {escape(str(topics_matched))}")
            lines.append(f"📅 Time: {escape(timestamp)}")
            message = "\n".join(lines)
        elif event_type == "summaries_generated":
            summaries_count = details.get('summaries_count', 'N/A')
            users_count = details.get('users_count', 'N/A')
            duration = details.get('duration', 'N/A')
            lines = [
                "📋 <b>Summaries Generated</b>\n",
                f"📊 Summaries Created: {escape(str(summaries_count))}",
                f"👥 Users Served: {escape(str(users_count))}",
                f"⏱️ Duration: {escape(str(duration))}s",
            ]
            if 'failed_count' in details:
                lines.append(f"❌ Failed: {escape(str(details.get('failed_count')))}")
            lines.append(f"📅 Time: {escape(timestamp)}")
            message = "\n".join(lines)
        elif event_type == "summaries_sent":
            sent_count = details.get('sent_count', 'N/A')
            failed_count = details.get('failed_count', 'N/A')
            message = (
                f"📤 <b>Daily Summaries Sent</b>\n\n"
                f"✅ Successfully Sent: {escape(str(sent_count))}\n"
                f"❌ Failed: {escape(str(failed_count))}\n"
                f"📅 Time: {escape(timestamp)}"
            )
        elif event_type == "cleanup_completed":
            vectors_cleaned = details.get('vectors_cleaned', 'N/A')
            message = (
                f"🧹 <b>Cleanup Completed</b>\n\n"
                f"🗑️ Old Vectors Removed: {escape(str(vectors_cleaned))}\n"
                f"📅 Time: {escape(timestamp)}"
            )
        else:
            message = (
                f"⚙️ <b>System Event</b>\n\n"
                f"🔄 Event: {escape(str(event_type))}\n"
                f"📋 Details: {escape(str(details))}\n"
                f"📅 Time: {escape(timestamp)}"
            )
        
        await self._send_notification(message)
    
    async def notify_error(self, error_type: str, error_message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Notify admin about system errors."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        context_str = ""
        if context:
            context_str = f"\n📋 Context: {escape(str(context))}"
        
        message = (
            f"🚨 <b>System Error</b>\n\n"
            f"❌ Type: {escape(str(error_type))}\n"
            f"💬 Message: <code>{escape(str(error_message))}</code>{context_str}\n"
            f"📅 Time: {escape(timestamp)}"
        )
        await self._send_notification(message)
    
    async def notify_daily_stats(self, stats: Dict[str, Any]) -> None:
        """Send daily statistics summary."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        message = (
            f"📊 <b>Daily Statistics</b>\n\n"
            f"👥 Total Users: {escape(str(stats.get('total_users', 'N/A')))}\n"
            f"🆕 New Users Today: {escape(str(stats.get('new_users_today', 'N/A')))}\n"
            f"📨 Messages Collected: {escape(str(stats.get('messages_collected', 'N/A')))}\n"
            f"🎯 Messages Filtered: {escape(str(stats.get('messages_filtered', 'N/A')))}\n"
            f"📋 Summaries Generated: {escape(str(stats.get('summaries_generated', 'N/A')))}\n"
            f"📤 Summaries Sent: {escape(str(stats.get('summaries_sent', 'N/A')))}\n"
            f"❌ Errors Today: {escape(str(stats.get('errors_today', 'N/A')))}\n"
            f"🚫 Blocked Users: {escape(str(stats.get('blocked_users', 'N/A')))}\n"
            f"😴 Inactive Users: {escape(str(stats.get('inactive_users', 'N/A')))}\n"
            f"📅 Date: {escape(timestamp)}"
        )
        await self._send_notification(message)


# Global notifier instance - will be initialized in telegram_bot.py
notifier: Optional[Notifier] = None


def get_notifier() -> Optional[Notifier]:
    """Get the global notifier instance."""
    return notifier


def set_notifier(notification_instance: Notifier) -> None:
    """Set the global notifier instance."""
    global notifier
    notifier = notification_instance 