import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from telegram import Bot
from telegram.error import Forbidden, TelegramError

from db.database import SessionLocal
from db.models import User
from utils.monitoring import get_notifier

logger = logging.getLogger(__name__)


class UserStatusTracker:
    """Tracks user status changes including bot blocking and churn detection."""
    
    def __init__(self):
        self.blocked_users: Set[int] = set()
        self.last_activity: Dict[int, datetime] = {}
    
    async def check_user_blocked(self, bot: Bot, user_id: int, username: str) -> bool:
        """Check if a user has blocked the bot by attempting to send a test message."""
        try:
            await bot.get_chat_member(chat_id=user_id, user_id=bot.id)
            
            if user_id in self.blocked_users:
                self.blocked_users.remove(user_id)
                notifier = get_notifier()
                if notifier:
                    await notifier.notify_user_returned(username, user_id)
                logger.info(f"User {user_id} (@{username}) has unblocked the bot")
                return False
            
            return False
            
        except Forbidden:
            # User has blocked the bot
            if user_id not in self.blocked_users:
                self.blocked_users.add(user_id)
                notifier = get_notifier()
                if notifier:
                    await notifier.notify_bot_blocked(username, user_id)
                logger.info(f"User {user_id} (@{username}) has blocked the bot")
            return True
            
        except TelegramError as e:
            logger.error(f"Error checking user {user_id} status: {e}")
            return False
    
    async def handle_message_send_error(self, error: Exception, user_id: int, username: str) -> bool:
        """Handle errors when sending messages to users and detect bot blocking."""
        if isinstance(error, Forbidden):
            if user_id not in self.blocked_users:
                self.blocked_users.add(user_id)
                notifier = get_notifier()
                if notifier:
                    await notifier.notify_bot_blocked(username, user_id)
                logger.info(f"User {user_id} (@{username}) has blocked the bot")
            return True
        return False
    
    def update_user_activity(self, user_id: int) -> None:
        """Update the last activity timestamp for a user."""
        self.last_activity[user_id] = datetime.now()
    
    async def check_inactive_users(self, inactive_days_threshold: int = 7) -> List[Dict]:
        """Check for users who haven't been active for a specified number of days."""
        inactive_users = []
        threshold_date = datetime.now() - timedelta(days=inactive_days_threshold)
        
        with SessionLocal() as session:
            users = session.query(User).all()
            
            for user in users:
                user_id = user.id
                telegram_id = user.telegram_id
                username = user.username
                
                if telegram_id in self.blocked_users:
                    continue
                
                last_seen = self.last_activity.get(user_id)
                
                if not last_seen:
                    last_seen = user.created_at
                
                if last_seen and last_seen < threshold_date:
                    days_inactive = (datetime.now() - last_seen).days
                    inactive_users.append({
                        'user_id': user_id,
                        'telegram_id': telegram_id,
                        'username': username,
                        'days_inactive': days_inactive,
                        'last_seen': last_seen
                    })
        
        return inactive_users
    
    async def notify_inactive_users(self, inactive_days_threshold: int = 7) -> None:
        """Notify admin about inactive users (potential churn)."""
        inactive_users = await self.check_inactive_users(inactive_days_threshold)
        
        notifier = get_notifier()
        if not notifier:
            return
        
        for user_info in inactive_users:
            await notifier.notify_user_inactive(
                username=user_info['username'],
                telegram_id=user_info['telegram_id'],
                days_inactive=user_info['days_inactive']
            )


# Global user tracker instance
user_tracker: Optional[UserStatusTracker] = None


def get_user_tracker() -> Optional[UserStatusTracker]:
    """Get the global user tracker instance."""
    return user_tracker


def set_user_tracker(tracker_instance: UserStatusTracker) -> None:
    """Set the global user tracker instance."""
    global user_tracker
    user_tracker = tracker_instance


def init_user_tracker() -> UserStatusTracker:
    """Initialize and return a new user tracker instance."""
    tracker = UserStatusTracker()
    set_user_tracker(tracker)
    return tracker 