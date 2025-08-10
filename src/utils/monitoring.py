import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
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
    
    async def _send_notification(self, message: str, parse_mode: str = 'Markdown') -> bool:
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
            f"🚫 **Bot Blocked**\n\n"
            f"👤 User: @{username}\n"
            f"🆔 Telegram ID: `{telegram_id}`\n"
            f"❌ Status: Bot has been blocked by user\n"
            f"🕒 Time: {timestamp}"
        )
        await self._send_notification(message)
    
    async def notify_user_returned(self, username: str, telegram_id: int) -> None:
        """Notify admin when a previously blocked user returns."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = (
            f"✅ **User Returned**\n\n"
            f"👤 User: @{username}\n"
            f"🆔 Telegram ID: `{telegram_id}`\n"
            f"🔓 Status: User unblocked the bot\n"
            f"🕒 Time: {timestamp}"
        )
        await self._send_notification(message)
    
    async def notify_user_inactive(self, username: str, telegram_id: int, days_inactive: int) -> None:
        """Notify admin about inactive users (potential churn)."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = (
            f"😴 **Inactive User Alert**\n\n"
            f"👤 User: @{username}\n"
            f"🆔 Telegram ID: `{telegram_id}`\n"
            f"📅 Days Inactive: {days_inactive}\n"
            f"⚠️ Status: Potential churn risk\n"
            f"🕒 Time: {timestamp}"
        )
        await self._send_notification(message)

    async def notify_new_user(self, username: str, telegram_id: int, user_count: int) -> None:
        """Notify admin about new user registration."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = (
            f"🆕 **New User Registered**\n\n"
            f"👤 Username: @{username}\n"
            f"🆔 Telegram ID: `{telegram_id}`\n"
            f"📊 Total Users: {user_count}\n"
            f"🕒 Time: {timestamp}"
        )
        await self._send_notification(message)
    
    async def notify_user_activity(self, username: str, activity_type: str, details: Dict[str, Any]) -> None:
        """Notify admin about user activity (topics/sources changes)."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if activity_type == "topics_added":
            topics = ", ".join(details.get("topics", []))
            message = (
                f"📝 **Topics Added**\n\n"
                f"👤 User: @{username}\n"
                f"➕ Added: {topics}\n"
                f"📊 Total Topics: {details.get('total_count', 'N/A')}\n"
                f"🕒 Time: {timestamp}"
            )
        elif activity_type == "sources_added":
            sources = ", ".join(details.get("sources", []))
            message = (
                f"📡 **Sources Added**\n\n"
                f"👤 User: @{username}\n"
                f"➕ Added: {sources}\n"
                f"📊 Total Sources: {details.get('total_count', 'N/A')}\n"
                f"🕒 Time: {timestamp}"
            )
        elif activity_type == "topics_removed":
            message = (
                f"🗑️ **Topic Removed**\n\n"
                f"👤 User: @{username}\n"
                f"➖ Removed: {details.get('topic', 'N/A')}\n"
                f"📊 Remaining Topics: {details.get('total_count', 'N/A')}\n"
                f"🕒 Time: {timestamp}"
            )
        elif activity_type == "sources_removed":
            message = (
                f"🗑️ **Source Removed**\n\n"
                f"👤 User: @{username}\n"
                f"➖ Removed: {details.get('source', 'N/A')}\n"
                f"📊 Remaining Sources: {details.get('total_count', 'N/A')}\n"
                f"🕒 Time: {timestamp}"
            )
        else:
            message = (
                f"📊 **User Activity**\n\n"
                f"👤 User: @{username}\n"
                f"🔄 Activity: {activity_type}\n"
                f"📋 Details: {str(details)}\n"
                f"🕒 Time: {timestamp}"
            )
        
        await self._send_notification(message)
    
    async def notify_system_performance(self, event_type: str, details: Dict[str, Any]) -> None:
        """Notify admin about system performance events."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if event_type == "collection_started":
            message = (
                f"🔄 **Collection Started**\n\n"
                f"📅 Time: {timestamp}\n"
                f"🔄 Type: {'Initial' if details.get('is_initial') else 'Regular'}"
            )
        elif event_type == "collection_completed":
            duration = details.get('duration', 'N/A')
            messages_collected = details.get('messages_collected', 'N/A')
            messages_processed = details.get('messages_processed')
            skipped_empty = details.get('skipped_empty')
            skipped_old = details.get('skipped_old')
            lines = [
                "✅ **Collection Completed**\n",
                f"📊 Messages Collected: {messages_collected}",
                f"⏱️ Duration: {duration}s",
            ]
            if messages_processed is not None:
                lines.append(f"🧮 Messages Processed: {messages_processed}")
            if skipped_empty is not None:
                lines.append(f"🚫 Skipped (empty): {skipped_empty}")
            if skipped_old is not None:
                lines.append(f"⏳ Skipped (too old): {skipped_old}")
            lines.append(f"📅 Time: {timestamp}")
            message = "\n".join(lines)
        elif event_type == "filtering_completed":
            filtered_count = details.get('filtered_messages', 'N/A')
            users_processed = details.get('users_processed')
            topics_matched = details.get('topics_matched')
            duration = details.get('duration', 'N/A')
            lines = [
                "🎯 **Filtering Completed**\n",
                f"📊 Messages Filtered: {filtered_count}",
                f"⏱️ Duration: {duration}s",
            ]
            if users_processed is not None:
                lines.append(f"👥 Users Processed: {users_processed}")
            if topics_matched is not None:
                lines.append(f"🏷️ Topics Matched: {topics_matched}")
            lines.append(f"📅 Time: {timestamp}")
            message = "\n".join(lines)
        elif event_type == "summaries_generated":
            summaries_count = details.get('summaries_count', 'N/A')
            users_count = details.get('users_count', 'N/A')
            duration = details.get('duration', 'N/A')
            lines = [
                "📋 **Summaries Generated**\n",
                f"📊 Summaries Created: {summaries_count}",
                f"👥 Users Served: {users_count}",
                f"⏱️ Duration: {duration}s",
            ]
            if 'failed_count' in details:
                lines.append(f"❌ Failed: {details.get('failed_count')}")
            lines.append(f"📅 Time: {timestamp}")
            message = "\n".join(lines)
        elif event_type == "summaries_sent":
            sent_count = details.get('sent_count', 'N/A')
            failed_count = details.get('failed_count', 'N/A')
            message = (
                f"📤 **Daily Summaries Sent**\n\n"
                f"✅ Successfully Sent: {sent_count}\n"
                f"❌ Failed: {failed_count}\n"
                f"📅 Time: {timestamp}"
            )
        elif event_type == "cleanup_completed":
            vectors_cleaned = details.get('vectors_cleaned', 'N/A')
            message = (
                f"🧹 **Cleanup Completed**\n\n"
                f"🗑️ Old Vectors Removed: {vectors_cleaned}\n"
                f"📅 Time: {timestamp}"
            )
        else:
            message = (
                f"⚙️ **System Event**\n\n"
                f"🔄 Event: {event_type}\n"
                f"📋 Details: {str(details)}\n"
                f"📅 Time: {timestamp}"
            )
        
        await self._send_notification(message)
    
    async def notify_error(self, error_type: str, error_message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Notify admin about system errors."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        context_str = ""
        if context:
            context_str = f"\n📋 Context: {str(context)}"
        
        message = (
            f"🚨 **System Error**\n\n"
            f"❌ Type: {error_type}\n"
            f"💬 Message: `{error_message}`{context_str}\n"
            f"📅 Time: {timestamp}"
        )
        await self._send_notification(message)
    
    async def notify_daily_stats(self, stats: Dict[str, Any]) -> None:
        """Send daily statistics summary."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        message = (
            f"📊 **Daily Statistics**\n\n"
            f"👥 Total Users: {stats.get('total_users', 'N/A')}\n"
            f"🆕 New Users Today: {stats.get('new_users_today', 'N/A')}\n"
            f"📨 Messages Collected: {stats.get('messages_collected', 'N/A')}\n"
            f"🎯 Messages Filtered: {stats.get('messages_filtered', 'N/A')}\n"
            f"📋 Summaries Generated: {stats.get('summaries_generated', 'N/A')}\n"
            f"📤 Summaries Sent: {stats.get('summaries_sent', 'N/A')}\n"
            f"❌ Errors Today: {stats.get('errors_today', 'N/A')}\n"
            f"🚫 Blocked Users: {stats.get('blocked_users', 'N/A')}\n"
            f"😴 Inactive Users: {stats.get('inactive_users', 'N/A')}\n"
            f"📅 Date: {timestamp}"
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