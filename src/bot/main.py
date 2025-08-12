import os
import logging
import time
from typing import List
from datetime import time as dt_time
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from zoneinfo import ZoneInfo

from db.database import SessionLocal, create_tables
from db.models import User
from db.qdrant_utils import cleanup_old_vectors
from pipeline.collector import run_collection
from pipeline.filter import filter_messages_async
from pipeline.summarizer import generate_summaries_async, get_user_summaries
from utils.monitoring import Notifier, set_notifier, get_notifier
from utils.user_tracker import init_user_tracker, get_user_tracker
from utils.logging_config import setup_logging
from utils.text_utils import split_text_safely
from utils.stats_tracker import get_user_stats, calculate_time_saved, format_time_duration
from utils.i18n import Language, get_text

from .handlers import (
    start, unknown_command, error_handler, prompt_start,
    main_menu_handler, add_topics, add_sources, handle_removal, handle_language_selection,
    CHOOSING_ACTION, ADDING_TOPICS, ADDING_SOURCES, REMOVING_ITEMS, SELECTING_LANGUAGE
)

logger = logging.getLogger(__name__)


async def collect_and_filter_messages(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled job to collect and filter messages."""
    logger.info("Running collection and filtering")
    start_time = time.time()
    
    notifier = get_notifier()
    if notifier:
        await notifier.notify_system_performance("collection_started", {"is_initial": False})

    try:
        collected_total, collected_stats = await run_collection()
        
        collection_duration = time.time() - start_time
        filter_start_time = time.time()
        
        filter_result = await filter_messages_async()
        
        filtering_duration = time.time() - filter_start_time
        
        logger.info("Collection and filtering finished")
        
        if notifier:
            await notifier.notify_system_performance("collection_completed", {
                "duration": round(collection_duration, 2),
                "messages_collected": collected_total,
                "messages_processed": collected_stats.get("messages_processed", "N/A"),
                "skipped_empty": collected_stats.get("skipped_empty", "N/A"),
                "skipped_old": collected_stats.get("skipped_old", "N/A"),
            })
            await notifier.notify_system_performance("filtering_completed", {
                "duration": round(filtering_duration, 2),
                "filtered_messages": filter_result.get("messages_filtered", "N/A"),
                "users_processed": filter_result.get("users_processed", "N/A"),
                "topics_matched": filter_result.get("topics_matched", "N/A"),
            })
    except Exception as e:
        logger.exception(f"Collection and filtering failed: {e}")
        if notifier:
            await notifier.notify_error("Collection/Filtering", str(e), {"is_initial": False})


async def send_daily_summaries(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send daily summaries to all users."""
    logger.info("Running daily summary job")
    start_time = time.time()
    
    notifier = get_notifier()
    summaries_count = 0
    users_count = 0
    sent_count = 0
    failed_count = 0

    try:
        await generate_summaries_async(days_back=1)
        generation_duration = time.time() - start_time
    except Exception as e:
        logger.exception(f"Failed to generate summaries: {e}")
        if notifier:
            await notifier.notify_error("Summary Generation", str(e))
        return

    with SessionLocal() as session:
        users: List[User] = session.query(User).filter(User.telegram_id.isnot(None)).all()
        users_count = len(users)
        tracker = get_user_tracker()

        for user in users:
            if tracker and user.telegram_id in tracker.blocked_users:
                logger.info(f"Skipping user {user.id} (blocked bot)")
                continue
            
            summaries = get_user_summaries(user.id, days_back=1)
            if not summaries:
                try:
                    user_lang = Language(user.language) if getattr(user, "language", None) else Language.ENGLISH
                except Exception:
                    user_lang = Language.ENGLISH
                user_stats = get_user_stats(user.id, days_back=1)
                time_analysis = calculate_time_saved(user_stats) if user_stats else None
                stats_lines: list[str] = []
                if user_stats and time_analysis:
                    stats_lines.append(f"\n\n{get_text('stats_title', user_lang)}")
                    if hasattr(user_stats, "messages_collected"):
                        stats_lines.append(f"{get_text('stats_messages_collected', user_lang)} {user_stats.messages_collected}")
                    has_topics = bool(getattr(user, "user_topics", []))
                    if has_topics and hasattr(user_stats, "messages_filtered"):
                        matched = getattr(user_stats, "topics_matched", 0)
                        stats_lines.append(
                            f"{get_text('stats_messages_filtered', user_lang)} {user_stats.messages_filtered} ("
                            + get_text('stats_matched_topics_suffix', user_lang, count=matched)
                            + ")"
                        )
                    if not has_topics and hasattr(user_stats, "sources_processed"):
                        stats_lines.append(f"{get_text('stats_sources_processed', user_lang)} {user_stats.sources_processed}")
                    if time_analysis.get("time_saved", 0) > 0:
                        stats_lines.append(
                            f"{get_text('stats_time_saved', user_lang)} ~{format_time_duration(time_analysis['time_saved'], user_lang)} ("
                            + get_text('stats_vs_manual', user_lang)
                            + ")"
                        )
                        stats_lines.append(
                            f"{get_text('stats_efficiency', user_lang)} {time_analysis['efficiency_ratio']:.1f}"
                            + get_text('stats_efficiency_suffix', user_lang)
                        )
                message_no_updates = get_text('nothing_interesting', user_lang) + ("\n".join(stats_lines) if stats_lines else "")
                try:
                    await context.bot.send_message(
                        chat_id=user.telegram_id,
                        text=message_no_updates,
                    )
                    logger.info(f"Sent 'no updates' message to user {user.id} (chat {user.telegram_id})")
                    sent_count += 1
                except Exception as e:
                    if tracker:
                        await tracker.handle_message_send_error(e, user.telegram_id, user.username)
                    logger.error(
                        f"Failed to send 'no updates' message to user {user.id} (chat {user.telegram_id}): {e}"
                    )
                    failed_count += 1
                continue

            summary = summaries[0]
            summaries_count += 1
            message_text = summary.content

            # Split text safely to avoid breaking formatting entities
            chunks = split_text_safely(message_text, max_chunk_size=4096)
            user_failed = False
            for chunk in chunks:
                try:
                    await context.bot.send_message(
                        chat_id=user.telegram_id,
                        text=chunk,
                        parse_mode="HTML",
                    )
                except Exception as e:
                    if tracker:
                        await tracker.handle_message_send_error(e, user.telegram_id, user.username)
                    logger.error(
                        f"Failed to send summary chunk to user {user.id} (chat {user.telegram_id}): {e}"
                    )
                    user_failed = True
                    break
            
            if user_failed:
                failed_count += 1
            else:
                sent_count += 1
    
    total_duration = time.time() - start_time
    
    # Notify admin about summary generation and sending
    if notifier:
        await notifier.notify_system_performance("summaries_generated", {
            "summaries_count": summaries_count,
            "users_count": users_count,
            "duration": round(generation_duration, 2)
        })
        await notifier.notify_system_performance("summaries_sent", {
            "sent_count": sent_count,
            "failed_count": failed_count
        })


async def cleanup_old_vectors_job(context: ContextTypes.DEFAULT_TYPE, days_to_keep: int = 30) -> None:
    """Scheduled job to cleanup old vectors."""
    logger.info("Running cleanup of old vectors")
    
    notifier = get_notifier()

    try:
        await cleanup_old_vectors(days_to_keep=days_to_keep)
        
        if notifier:
            await notifier.notify_system_performance("cleanup_completed", {
                "vectors_cleaned": "N/A"  # Would need to modify cleanup_old_vectors to return count
            })
    except Exception as e:
        logger.exception(f"Cleanup of old vectors failed: {e}")
        if notifier:
            await notifier.notify_error("Vector Cleanup", str(e), {"days_to_keep": days_to_keep})


async def check_inactive_users_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check for inactive users and notify admin."""
    logger.info("Checking for inactive users")
    
    tracker = get_user_tracker()
    if tracker:
        try:
            await tracker.notify_inactive_users(inactive_days_threshold=7)
            logger.info("Inactive users check completed")
        except Exception as e:
            logger.exception(f"Failed to check inactive users: {e}")
            notifier = get_notifier()
            if notifier:
                await notifier.notify_error("Inactive Users Check", str(e))


def main() -> None:
    """Run the bot."""
    load_dotenv()
    
    setup_logging()
    
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN environment variable not set!")
        return
    
    application = Application.builder().token(token).build()

    notifier = Notifier(application.bot)
    set_notifier(notifier)
    
    user_tracker = init_user_tracker()
    
    kyiv_tz = ZoneInfo("Europe/Kyiv")

    # Setup scheduled jobs
    application.job_queue.run_daily(
        collect_and_filter_messages,
        time=dt_time(hour=17, minute=45, tzinfo=kyiv_tz),
        name="collection_and_filtering",
    )

    application.job_queue.run_daily(
        send_daily_summaries,
        time=dt_time(hour=18, minute=0, tzinfo=kyiv_tz),
        name="daily_summaries",
    )

    application.job_queue.run_repeating(
        cleanup_old_vectors_job,
        interval=7 * 24 * 60 * 60,  # 7 days in seconds
        first=dt_time(hour=17, minute=0, tzinfo=kyiv_tz),
        name="cleanup_old_vectors",
    )

    # Check for inactive users daily at 19:00 Kyiv time
    application.job_queue.run_daily(
        check_inactive_users_job,
        time=dt_time(hour=19, minute=0, tzinfo=kyiv_tz),
        name="check_inactive_users",
    )
    
    # Setup conversation handler
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
        ],
        states={
            CHOOSING_ACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler),
            ],
            ADDING_TOPICS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_topics)
            ],
            ADDING_SOURCES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_sources)
            ],
            REMOVING_ITEMS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_removal),
            ],
            SELECTING_LANGUAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_language_selection),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )
    
    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    # If user types anything in a private chat outside of the conversation, prompt a one-time 
    # keyboard with /start so they can easily restart without typing the command.
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            prompt_start
        )
    )
    
    application.add_error_handler(error_handler)
    
    # Initialize database
    create_tables()
    
    logger.info("Bot started successfully!")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()