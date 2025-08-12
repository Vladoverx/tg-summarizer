import logging
import time
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from sqlalchemy.orm.attributes import flag_modified
from zoneinfo import ZoneInfo

from db.database import SessionLocal
from db.models import User, Source, UserTopic
from pipeline.collector import run_collection, TelegramCollector
from pipeline.filter import filter_messages_async
from pipeline.summarizer import generate_summaries_async, get_user_summaries
from utils.monitoring import get_notifier
from utils.user_tracker import get_user_tracker
from utils.source_validator import validate_sources_batch, format_validation_result
from utils.i18n import Language, detect_user_language, get_text
from utils.text_utils import split_text_safely
from utils.stats_tracker import get_user_stats, calculate_time_saved, format_time_duration

from .keyboards import (
    get_user_language, is_admin_user, get_main_menu_keyboard, 
    get_testing_menu_keyboard, get_topics_menu_keyboard, 
    get_sources_menu_keyboard, get_language_selection_keyboard
)

logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_ACTION, ADDING_TOPICS, ADDING_SOURCES, REMOVING_ITEMS, SELECTING_LANGUAGE = range(5)

# Limits and validation rules
MAX_SOURCES_PER_USER = 40
MAX_TOPICS_PER_USER = 20
MAX_TOPIC_WORDS = 7
MAX_TOPIC_CHARS = 70

def _is_valid_topic(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if len(cleaned) > MAX_TOPIC_CHARS:
        return False
    if len(cleaned.split()) > MAX_TOPIC_WORDS:
        return False
    return True


def get_time_until_next_summary(lang: Language) -> str:
    """Calculate time remaining until next daily summary, localized to user's language."""
    kyiv_tz = ZoneInfo("Europe/Kyiv")
    now = datetime.now(kyiv_tz)
    
    # Summary runs at 18:00 Kyiv time
    summary_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
    
    if now >= summary_time:
        summary_time += timedelta(days=1)
    
    time_diff = summary_time - now
    
    hours = int(time_diff.total_seconds() // 3600)
    minutes = int((time_diff.total_seconds() % 3600) // 60)
    
    if hours > 0:
        return f"{hours} {get_text('duration_hours', lang)} {minutes} {get_text('duration_minutes', lang)}"
    else:
        return f"{minutes} {get_text('duration_minutes', lang)}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and introduce the bot."""
    user = update.effective_user
    is_new_user = False
    
    with SessionLocal.begin() as session:
        db_user = session.query(User).filter(User.telegram_id == user.id).first()

        if not db_user:
            detected_lang = detect_user_language(user.language_code)
            
            db_user = User(
                username=user.username or str(user.id),
                telegram_id=user.id,
                language=detected_lang.value
            )
            session.add(db_user)
            is_new_user = True
        else:
            if db_user.telegram_id != user.id:
                db_user.telegram_id = user.id
            
            current_username = user.username or str(user.id)
            if db_user.username != current_username:
                db_user.username = current_username
            
            detected_lang = detect_user_language(user.language_code)
            if not db_user.language or db_user.language != detected_lang.value:
                db_user.language = detected_lang.value
            
        
        tracker = get_user_tracker()
        if tracker:
            tracker.update_user_activity(db_user.id)
        
        if is_new_user:
            notifier = get_notifier()
            if notifier:
                session.flush()
                total_users = session.query(User).count()
                await notifier.notify_new_user(
                    username=user.username or str(user.id),
                    telegram_id=user.id,
                    user_count=total_users
                )
    
    lang = get_user_language(user.id)
    welcome_message = get_text('welcome_message', lang, name=user.first_name)
    
    await update.message.reply_text(welcome_message, reply_markup=get_main_menu_keyboard(user.id))
    return CHOOSING_ACTION


async def prompt_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt the user to press /start with a one-time keyboard in private chats."""
    user = update.effective_user
    try:
        lang = get_user_language(user.id) if user else Language.ENGLISH
    except Exception:
        lang = Language.ENGLISH
    keyboard = ReplyKeyboardMarkup([["/start"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        get_text('unknown_command', lang),
        reply_markup=keyboard
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display help information."""
    user = update.effective_user
    lang = get_user_language(user.id)
    
    help_text = (
        f"{get_text('help_title', lang)}\n\n"
        f"{get_text('help_features', lang)}\n"
        f"{get_text('feature_topics', lang)}\n\n"
        f"{get_text('feature_sources', lang)}\n\n"
        f"{get_text('feature_summaries', lang)}\n\n"
        f"{get_text('help_how_it_works', lang)}\n"
        f"{get_text('how_it_works_1', lang)}\n"
        f"{get_text('how_it_works_2', lang)}\n"
        f"{get_text('how_it_works_3', lang)}\n\n"
        f"{get_text('help_footer', lang)}"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def show_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show language selection menu."""
    user = update.effective_user
    lang = get_user_language(user.id)
    
    await update.message.reply_text(
        get_text('select_language', lang),
        reply_markup=get_language_selection_keyboard(user.id),
        parse_mode='Markdown'
    )
    return SELECTING_LANGUAGE


async def handle_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle language selection."""
    user = update.effective_user
    text = update.message.text
    current_lang = get_user_language(user.id)
    
    if text == get_text('btn_back_main', current_lang):
        await update.message.reply_text(
            get_text('back_to_main', current_lang),
            reply_markup=get_main_menu_keyboard(user.id)
        )
        return CHOOSING_ACTION
    
    new_language = None
    if text in [get_text('btn_ukrainian', current_lang), "🇺🇦 Українська"]:
        new_language = Language.UKRAINIAN
    elif text in [get_text('btn_english', current_lang), "🇺🇸 English"]:
        new_language = Language.ENGLISH
    
    if new_language:
        # Update language inside a transaction, then send the keyboard AFTER commit
        updated_language = False
        with SessionLocal.begin() as session:
            db_user = session.query(User).filter(User.telegram_id == user.id).first()
            if db_user:
                db_user.language = new_language.value
                updated_language = True
                tracker = get_user_tracker()
                if tracker:
                    tracker.update_user_activity(db_user.id)

        if updated_language:
            # Now that the transaction has been committed, the keyboard will be built with the new language
            await update.message.reply_text(
                get_text('language_changed', new_language),
                reply_markup=get_main_menu_keyboard(user.id)
            )
            return CHOOSING_ACTION
    
    await update.message.reply_text(
        get_text('unknown_command', current_lang),
        reply_markup=get_language_selection_keyboard(user.id)
    )
    return SELECTING_LANGUAGE


async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle main menu selections."""
    user = update.effective_user
    text = update.message.text
    
    with SessionLocal() as session:
        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        if db_user:
            tracker = get_user_tracker()
            if tracker:
                tracker.update_user_activity(db_user.id)
    
    lang = get_user_language(user.id)
    
    if text == get_text('btn_help', lang):
        await help_command(update, context)
        return CHOOSING_ACTION
    
    elif text == get_text('btn_manage_topics', lang):
        await update.message.reply_text(
            f"{get_text('topics_management_title', lang)}\n\n"
            f"{get_text('topics_management_desc', lang)}\n\n"
            f"{get_text('prompt_what_to_do', lang)}",
            reply_markup=get_topics_menu_keyboard(user.id),
            parse_mode='Markdown'
        )
        return CHOOSING_ACTION
        
    elif text == get_text('btn_manage_sources', lang):
        await update.message.reply_text(
            f"{get_text('sources_management_title', lang)}\n\n"
            f"{get_text('sources_management_desc', lang)}\n\n"
            f"{get_text('prompt_what_to_do', lang)}",
            reply_markup=get_sources_menu_keyboard(user.id),
            parse_mode='Markdown'
        )
        return CHOOSING_ACTION
        
    elif text == get_text('btn_view_settings', lang):
        return await view_settings(update, context)
        
    elif text == get_text('btn_change_language', lang):
        return await show_language_selection(update, context)
        
    elif text == get_text('btn_testing', lang):
        if not is_admin_user(user.id):
            await update.message.reply_text(
                get_text('access_denied', lang),
                reply_markup=get_main_menu_keyboard(user.id)
            )
            return CHOOSING_ACTION
            
        await update.message.reply_text(
            f"{get_text('testing_menu_title', lang)}\n\n"
            f"{get_text('testing_menu_desc', lang)}",
            reply_markup=get_testing_menu_keyboard(user.id)
        )
        return CHOOSING_ACTION
        
    # Handle topics submenu
    elif text == get_text('btn_add_topics', lang):
        back_keyboard = [[get_text('btn_back_topics', lang)]]
        back_markup = ReplyKeyboardMarkup(back_keyboard, one_time_keyboard=True)
        
        await update.message.reply_text(
            f"{get_text('add_topics_title', lang)}\n\n"
            f"{get_text('add_topics_prompt', lang)}",
            reply_markup=back_markup,
            parse_mode='Markdown'
        )
        return ADDING_TOPICS
        
    elif text == get_text('btn_remove_topics', lang):
        return await remove_topics(update, context)
        
    elif text == get_text('btn_view_topics', lang):
        return await view_topics(update, context)
    
    # Handle sources submenu
    elif text == get_text('btn_add_sources', lang):
        back_keyboard = [[get_text('btn_back_sources', lang)]]
        back_markup = ReplyKeyboardMarkup(back_keyboard, one_time_keyboard=True)
        
        await update.message.reply_text(
            f"{get_text('add_sources_title', lang)}\n\n"
            f"{get_text('add_sources_prompt', lang)}",
            reply_markup=back_markup,
            parse_mode='Markdown'
        )
        return ADDING_SOURCES
        
    elif text == get_text('btn_remove_sources', lang):
        return await remove_sources(update, context)
        
    elif text == get_text('btn_view_sources', lang):
        return await view_sources(update, context)
        
    elif text == get_text('btn_back_main', lang):
        await update.message.reply_text(
            get_text('back_to_main', lang),
            reply_markup=get_main_menu_keyboard(user.id)
        )
        return CHOOSING_ACTION
    
    # Handle testing menu  
    elif text == get_text('btn_run_collection', lang):
        if not is_admin_user(user.id):
            await update.message.reply_text(
                get_text('testing_access_denied', lang),
                reply_markup=get_main_menu_keyboard(user.id)
            )
            return CHOOSING_ACTION
            
        await update.message.reply_text(
            get_text('collection_starting', lang),
            reply_markup=ReplyKeyboardRemove()
        )
        
        start_time = time.time()
        notifier = get_notifier()
        
        try:
            if notifier:
                await notifier.notify_system_performance("collection_started", {"is_initial": False, "manual": True})
            
            collected_total, collected_stats = await run_collection()
            collection_duration = time.time() - start_time
            filter_start_time = time.time()
            
            filter_result = await filter_messages_async()
            filtering_duration = time.time() - filter_start_time
            
            if notifier:
                await notifier.notify_system_performance("collection_completed", {
                    "duration": round(collection_duration, 2),
                    "messages_collected": collected_total,
                    "messages_processed": collected_stats.get("messages_processed", "N/A"),
                    "skipped_empty": collected_stats.get("skipped_empty", "N/A"),
                    "skipped_old": collected_stats.get("skipped_old", "N/A"),
                    "manual": True
                })
                await notifier.notify_system_performance("filtering_completed", {
                    "duration": round(filtering_duration, 2),
                    "filtered_messages": filter_result.get("messages_filtered", "N/A"),
                    "users_processed": filter_result.get("users_processed", "N/A"),
                    "topics_matched": filter_result.get("topics_matched", "N/A"),
                    "manual": True
                })
            
            await update.message.reply_text(
                get_text('collection_success', lang),
                reply_markup=get_main_menu_keyboard(user.id)
            )
        except Exception as e:
            logger.error(f"Manual collection and filtering failed: {e}")
            if notifier:
                await notifier.notify_error("Manual Collection/Filtering", str(e), {"user": user.username or str(user.id)})
            
            await update.message.reply_text(
                get_text('collection_failed', lang, error=str(e)),
                reply_markup=get_main_menu_keyboard(user.id)
            )
        
        return CHOOSING_ACTION
        
    elif text == get_text('btn_generate_summaries', lang):
        if not is_admin_user(user.id):
            await update.message.reply_text(
                get_text('testing_access_denied', lang),
                reply_markup=get_main_menu_keyboard(user.id)
            )
            return CHOOSING_ACTION
            
        await update.message.reply_text(
            get_text('summaries_generating', lang),
            reply_markup=ReplyKeyboardRemove()
        )
        
        start_time = time.time()
        notifier = get_notifier()
        summaries_count = 0
        users_count = 0
        sent_count = 0
        failed_count = 0
        
        try:
            await generate_summaries_async(days_back=1)
            generation_duration = time.time() - start_time
            
            with SessionLocal() as session:
                from typing import List
                users: List[User] = session.query(User).filter(User.telegram_id.isnot(None)).all()
                users_count = len(users)
                tracker = get_user_tracker()

                for db_user in users:
                    if tracker and db_user.telegram_id in tracker.blocked_users:
                        logger.info(f"Skipping user {db_user.id} (blocked bot)")
                        continue
                    
                    summaries = get_user_summaries(db_user.id, days_back=1)
                    if not summaries:
                        try:
                            user_lang = Language(db_user.language) if getattr(db_user, "language", None) else Language.ENGLISH
                        except Exception:
                            user_lang = Language.ENGLISH
                        user_stats = get_user_stats(db_user.id, days_back=1)
                        time_analysis = calculate_time_saved(user_stats) if user_stats else None
                        stats_lines: list[str] = []
                        if user_stats and time_analysis:
                            stats_lines.append(f"\n\n{get_text('stats_title', user_lang)}")
                            if hasattr(user_stats, "messages_collected"):
                                stats_lines.append(f"• {get_text('stats_messages_collected', user_lang)} {user_stats.messages_collected}")
                            has_topics = bool(getattr(db_user, "user_topics", []))
                            if has_topics and hasattr(user_stats, "messages_filtered"):
                                matched = getattr(user_stats, "topics_matched", 0)
                                stats_lines.append(
                                    f"• {get_text('stats_messages_filtered', user_lang)} {user_stats.messages_filtered} ("
                                    + get_text('stats_matched_topics_suffix', user_lang, count=matched)
                                    + ")"
                                )
                            if not has_topics and hasattr(user_stats, "sources_processed"):
                                stats_lines.append(f"• {get_text('stats_sources_processed', user_lang)} {user_stats.sources_processed}")
                            if time_analysis.get("time_saved", 0) > 0:
                                stats_lines.append(
                                    f"• {get_text('stats_time_saved', user_lang)} ~{format_time_duration(time_analysis['time_saved'], user_lang)} ("
                                    + get_text('stats_vs_manual', user_lang)
                                    + ")"
                                )
                                stats_lines.append(
                                    f"• {get_text('stats_efficiency', user_lang)} {time_analysis['efficiency_ratio']:.1f}"
                                    + get_text('stats_efficiency_suffix', user_lang)
                                )
                        message_no_updates = get_text('nothing_interesting', user_lang) + ("\n".join(stats_lines) if stats_lines else "")
                        try:
                            await context.bot.send_message(
                                chat_id=db_user.telegram_id,
                                text=message_no_updates,
                            )
                            logger.info(f"Sent 'no updates' message to user {db_user.id} (chat {db_user.telegram_id})")
                            sent_count += 1
                        except Exception as e:
                            if tracker:
                                await tracker.handle_message_send_error(e, db_user.telegram_id, db_user.username)
                            logger.error(
                                f"Failed to send 'no updates' message to user {db_user.id} (chat {db_user.telegram_id}): {e}"
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
                                chat_id=db_user.telegram_id,
                                text=chunk,
                                parse_mode="HTML",
                            )
                        except Exception as e:
                            if tracker:
                                await tracker.handle_message_send_error(e, db_user.telegram_id, db_user.username)
                            logger.error(
                                f"Failed to send summary chunk to user {db_user.id} (chat {db_user.telegram_id}): {e}"
                            )
                            user_failed = True
                            break
                    
                    if user_failed:
                        failed_count += 1
                    else:
                        sent_count += 1
                
                # Notify admin about summary generation and sending
                if notifier:
                    await notifier.notify_system_performance("summaries_generated", {
                        "summaries_count": summaries_count,
                        "users_count": users_count,
                        "duration": round(generation_duration, 2),
                        "manual": True,
                        "user": user.username or str(user.id)
                    })
                    await notifier.notify_system_performance("summaries_sent", {
                        "sent_count": sent_count,
                        "failed_count": failed_count,
                        "manual": True
                    })
                
                # Send confirmation to admin
                await update.message.reply_text(
                    f"✅ **Manual Summary Distribution Complete**\n\n"
                    f"📊 **Statistics:**\n"
                    f"• Generated summaries: {summaries_count}\n"
                    f"• Total users: {users_count}\n"
                    f"• Successfully sent: {sent_count}\n"
                    f"• Failed to send: {failed_count}\n"
                    f"• Generation time: {round(generation_duration, 2)}s",
                    reply_markup=get_main_menu_keyboard(user.id),
                    parse_mode='Markdown'
                )
                    
        except Exception as e:
            logger.error(f"Manual summary generation and distribution failed: {e}")
            if notifier:
                await notifier.notify_error("Manual Summary Generation", str(e), {"user": user.username or str(user.id)})
            
            await update.message.reply_text(
                get_text('summaries_failed', lang, error=str(e)),
                reply_markup=get_main_menu_keyboard(user.id)
            )
        
        return CHOOSING_ACTION
    
    else:
        await update.message.reply_text(
            get_text('unknown_command', lang),
            reply_markup=get_main_menu_keyboard(user.id)
        )
        return CHOOSING_ACTION


async def add_topics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Add topics to user's preferences."""
    user = update.effective_user
    topics_text = update.message.text.strip()
    
    # Handle back button
    lang = get_user_language(user.id)
    if topics_text == get_text('btn_back_topics', lang):
        await update.message.reply_text(
            f"{get_text('topics_management_title', lang)}\n\n"
            f"{get_text('topics_management_desc', lang)}\n\n"
            f"{get_text('prompt_what_to_do', lang)}",
            reply_markup=get_topics_menu_keyboard(user.id),
            parse_mode='Markdown'
        )
        return CHOOSING_ACTION
    
    if not topics_text:
        await update.message.reply_text(
            get_text('provide_topics', lang),
            reply_markup=get_topics_menu_keyboard(user.id)
        )
        return CHOOSING_ACTION
    
    # Parse topics from comma-separated string
    raw_topics = [topic.strip() for topic in topics_text.split(',') if topic.strip()]
    # Normalize to lowercase, keep original mapping for potential future use
    normalized_topics = [t.lower() for t in raw_topics]
    # Validate topic sizes
    valid_normalized_topics: list[str] = []
    invalid_topics: list[str] = []
    seen_normalized: set[str] = set()
    for raw, norm in zip(raw_topics, normalized_topics):
        if norm in seen_normalized:
            continue
        seen_normalized.add(norm)
        if _is_valid_topic(raw):
            valid_normalized_topics.append(norm)
        else:
            invalid_topics.append(raw)
    
    if not valid_normalized_topics:
        await update.message.reply_text(
            get_text('no_valid_topics', lang),
            reply_markup=get_topics_menu_keyboard(user.id)
        )
        return CHOOSING_ACTION
    
    # Update database
    with SessionLocal() as session:
        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        if db_user:
            existing_topics = {ut.topic for ut in db_user.user_topics}
            current_count = len(existing_topics)
            remaining_slots = max(0, MAX_TOPICS_PER_USER - current_count)

            if remaining_slots <= 0:
                await update.message.reply_text(
                    get_text('topics_limit_reached', lang, limit=MAX_TOPICS_PER_USER),
                    reply_markup=get_topics_menu_keyboard(user.id)
                )
                return CHOOSING_ACTION

            topics_added: list[str] = []
            skipped_duplicates: list[str] = []
            for topic in valid_normalized_topics:
                if topic in existing_topics or topic in topics_added:
                    skipped_duplicates.append(topic)
                    continue
                if remaining_slots <= 0:
                    break
                session.add(UserTopic(user_id=db_user.id, topic=topic))
                topics_added.append(topic)
                remaining_slots -= 1

            if topics_added:
                session.commit()

                # Notify admin about topics added
                notifier = get_notifier()
                if notifier:
                    await notifier.notify_user_activity(
                        username=user.username or str(user.id),
                        activity_type="topics_added",
                        details={
                            "topics": topics_added,
                            "total_count": len(existing_topics) + len(topics_added)
                        }
                    )

                tracker = get_user_tracker()
                if tracker:
                    tracker.update_user_activity(db_user.id)

                added_preview = ', '.join(topics_added)
                base_text = get_text('topics_added_success', lang, topics=added_preview)
                suffix_lines: list[str] = []
                if invalid_topics:
                    examples = ', '.join(invalid_topics[:3])
                    suffix_lines.append(get_text('topics_suffix_invalid', lang, count=len(invalid_topics), examples=examples))
                if skipped_duplicates:
                    suffix_lines.append(get_text('topics_suffix_duplicates', lang, count=len(skipped_duplicates)))
                if remaining_slots == 0 and (len(valid_normalized_topics) > len(topics_added)):
                    suffix_lines.append(get_text('topics_suffix_limit_reached', lang))
                suffix_text = ("\n\n" + "\n".join(suffix_lines)) if suffix_lines else ""

                await update.message.reply_text(
                    base_text + suffix_text,
                    reply_markup=get_topics_menu_keyboard(user.id),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    get_text('topics_nothing_added', lang),
                    reply_markup=get_topics_menu_keyboard(user.id)
                )
        else:
            await update.message.reply_text(
                get_text('user_not_found', lang),
                reply_markup=get_topics_menu_keyboard(user.id)
            )
    
    return CHOOSING_ACTION


async def add_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Add sources to user's preferences."""
    user = update.effective_user
    sources_text = update.message.text.strip()
    
    # Handle back button
    lang = get_user_language(user.id)
    if sources_text == get_text('btn_back_sources', lang):
        await update.message.reply_text(
            f"{get_text('sources_management_title', lang)}\n\n"
            f"{get_text('sources_management_desc', lang)}\n\n"
            f"{get_text('prompt_what_to_do', lang)}",
            reply_markup=get_sources_menu_keyboard(user.id),
            parse_mode='Markdown'
        )
        return CHOOSING_ACTION
    
    if not sources_text:
        await update.message.reply_text(
            get_text('provide_sources', lang),
            reply_markup=get_sources_menu_keyboard(user.id)
        )
        return CHOOSING_ACTION
    
    # Send validation in progress message
    validation_message = await update.message.reply_text(
        get_text('sources_validating', lang),
        reply_markup=ReplyKeyboardRemove()
    )
    
    try:
        # Get Telegram client for validation
        async with TelegramCollector() as collector:
            validation_result = await validate_sources_batch(collector.client, sources_text)
            
            await validation_message.delete()
            
            if not validation_result["valid"]:
                error_message = format_validation_result(validation_result)
                await update.message.reply_text(
                    error_message,
                    reply_markup=get_sources_menu_keyboard(user.id),
                    parse_mode='Markdown'
                )
                return CHOOSING_ACTION
            
            valid_sources = validation_result["valid_sources"]
            
            with SessionLocal.begin() as session:
                db_user = session.query(User).filter(User.telegram_id == user.id).first()
                if db_user:
                    current_count = len(db_user.sources) if db_user.sources else 0
                    remaining_slots = max(0, MAX_SOURCES_PER_USER - current_count)
                    if remaining_slots <= 0:
                        await update.message.reply_text(
                            get_text('sources_limit_reached', lang, limit=MAX_SOURCES_PER_USER),
                            reply_markup=get_sources_menu_keyboard(user.id)
                        )
                        return CHOOSING_ACTION

                    sources_added = []
                    sources_already_exist = []
                    sources_skipped_over_limit = []
                    for source_info in valid_sources:
                        normalized_source = source_info["normalized"]
                        # Store canonical username without leading '@' to avoid duplicates
                        canonical_username = normalized_source.lstrip('@')
                        source_obj = session.query(Source).filter(Source.username == canonical_username).first()
                        if not source_obj:
                            source_obj = Source(title=source_info["title"], username=canonical_username)
                            session.add(source_obj)
                            session.flush()
                        if source_obj not in db_user.sources:
                            if remaining_slots > 0:
                                db_user.sources.append(source_obj)
                                sources_added.append(source_info)
                                remaining_slots -= 1
                            else:
                                sources_skipped_over_limit.append(source_info)
                        else:
                            sources_already_exist.append(source_info)
                    if sources_added:
                        notifier = get_notifier()
                        if notifier:
                            await notifier.notify_user_activity(
                                username=user.username or str(user.id),
                                activity_type="sources_added",
                                details={
                                    "sources": [s["normalized"] for s in sources_added],
                                    "total_count": len(db_user.sources)
                                }
                            )

                        tracker = get_user_tracker()
                        if tracker:
                            tracker.update_user_activity(db_user.id)
                        
                        success_message = get_text('sources_added_success', lang, count=len(sources_added)) + "\n\n"
                        for source_info in sources_added:
                            verified_badge = "✓" if source_info["verified"] else ""
                            success_message += f"📡 **{source_info['title']}** {verified_badge}\n"
                            success_message += f"   └ `{source_info['normalized']}`\n\n"
                        if sources_already_exist:
                            success_message += get_text('sources_already_exist', lang, count=len(sources_already_exist)) + "\n"
                            for source_info in sources_already_exist:
                                success_message += f"• {source_info['title']}\n"
                        if sources_skipped_over_limit:
                            success_message += get_text('sources_limit_reached_suffix', lang, count=len(sources_skipped_over_limit)) + "\n"
                        success_message += "\n" + get_text('sources_monitor_note', lang)
                        await update.message.reply_text(
                            success_message,
                            reply_markup=get_sources_menu_keyboard(user.id),
                            parse_mode='Markdown'
                        )
                    else:
                        existing_message = get_text('sources_already_exist', lang, count=len(sources_already_exist)) + "\n\n"
                        for source_info in sources_already_exist:
                            existing_message += f"📡 **{source_info['title']}**\n"
                            existing_message += f"   └ `{source_info['normalized']}`\n\n"
                        await update.message.reply_text(
                            existing_message,
                            reply_markup=get_sources_menu_keyboard(user.id),
                            parse_mode='Markdown'
                        )
                else:
                    await update.message.reply_text(
                        get_text('user_not_found', lang),
                        reply_markup=get_sources_menu_keyboard(user.id)
                    )
            
            if validation_result["invalid_count"] > 0:
                error_summary = f"\n\n{get_text('sources_invalid_summary', lang, count=validation_result['invalid_count'])}\n"
                for error in validation_result["errors"]:
                    error_summary += f"• {error}\n"
                
                await update.message.reply_text(
                    error_summary,
                    parse_mode='Markdown'
                )
    
    except Exception as e:
        try:
            await validation_message.delete()
        except:
            pass
        
        logger.error(f"Error during source validation: {e}")
        await update.message.reply_text(
            get_text('validation_error', lang, error=str(e)),
            reply_markup=get_sources_menu_keyboard(user.id)
        )
    
    return CHOOSING_ACTION


async def view_topics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display user's current topics."""
    user = update.effective_user
    lang = get_user_language(user.id)
    
    with SessionLocal() as session:
        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        if db_user and db_user.user_topics:
            topics = [ut.topic for ut in db_user.user_topics]
            if topics:
                topics_text = '\n• '.join(sorted(topics))
                message = get_text('current_topics', lang, topics=topics_text)
            else:
                message = get_text('no_topics_added', lang)
        else:
            message = get_text('no_topics_added', lang)
    
    await update.message.reply_text(message, reply_markup=get_topics_menu_keyboard(user.id), parse_mode='Markdown')
    return CHOOSING_ACTION


async def view_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display user's current sources."""
    user = update.effective_user
    lang = get_user_language(user.id)
    
    with SessionLocal() as session:
        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        if db_user and db_user.sources:
            sources = [s.username for s in db_user.sources]
            sources_text = '\n• '.join(sources)
            message = get_text('current_sources', lang, sources=sources_text)
        else:
            message = get_text('no_sources_added', lang)
    
    await update.message.reply_text(message, reply_markup=get_sources_menu_keyboard(user.id))
    return CHOOSING_ACTION


async def remove_topics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Remove topics from user's preferences."""
    user = update.effective_user
    lang = get_user_language(user.id)
    
    with SessionLocal.begin() as session:
        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        if not db_user or not db_user.user_topics:
            await update.message.reply_text(
                get_text('no_topics_to_remove', lang),
                reply_markup=get_topics_menu_keyboard(user.id)
            )
            return CHOOSING_ACTION
        
        topics = [ut.topic for ut in db_user.user_topics]
        if topics:
            topics_keyboard = [[topic] for topic in topics]
            topics_keyboard.append([get_text('btn_back_topics', lang)])
            topics_markup = ReplyKeyboardMarkup(topics_keyboard, one_time_keyboard=True)
            
            await update.message.reply_text(
                get_text('remove_topics_title', lang),
                reply_markup=topics_markup,
                parse_mode='Markdown'
            )
            context.user_data['removing_topics'] = True
            return REMOVING_ITEMS
    
    await update.message.reply_text(
        get_text('no_topics_to_remove', lang),
        reply_markup=get_topics_menu_keyboard(user.id)
    )
    return CHOOSING_ACTION


async def remove_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Remove sources from user's preferences."""
    user = update.effective_user
    lang = get_user_language(user.id)
    
    with SessionLocal() as session:
        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        if not db_user or not db_user.sources:
            await update.message.reply_text(
                get_text('no_sources_to_remove', lang),
                reply_markup=get_sources_menu_keyboard(user.id)
            )
            return CHOOSING_ACTION
        
        sources_keyboard = [[source.username] for source in db_user.sources]
        sources_keyboard.append([get_text('btn_back_sources', lang)])
        sources_markup = ReplyKeyboardMarkup(sources_keyboard, one_time_keyboard=True)
        
        await update.message.reply_text(
            get_text('remove_sources_title', lang),
            reply_markup=sources_markup,
            parse_mode='Markdown'
        )
        context.user_data['removing_sources'] = True
        return REMOVING_ITEMS
    
    await update.message.reply_text(
        get_text('no_sources_to_remove', lang),
        reply_markup=get_sources_menu_keyboard(user.id)
    )
    return REMOVING_ITEMS


async def handle_removal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle topic/source removal."""
    user = update.effective_user
    text = update.message.text
    lang = get_user_language(user.id)
    
    if text == get_text('btn_back_topics', lang):
        context.user_data.pop('removing_topics', None)
        await update.message.reply_text(
            f"{get_text('topics_management_title', lang)}\n\n"
            f"{get_text('topics_management_desc', lang)}\n\n"
            "What would you like to do?",
            reply_markup=get_topics_menu_keyboard(user.id),
            parse_mode='Markdown'
        )
        return CHOOSING_ACTION
    
    if text == get_text('btn_back_sources', lang):
        context.user_data.pop('removing_sources', None)
        await update.message.reply_text(
            f"{get_text('sources_management_title', lang)}\n\n"
            f"{get_text('sources_management_desc', lang)}\n\n"
            "What would you like to do?",
            reply_markup=get_sources_menu_keyboard(user.id),
            parse_mode='Markdown'
        )
        return CHOOSING_ACTION
    
    with SessionLocal.begin() as session:
        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        
        if context.user_data.get('removing_topics') and db_user:
            ut: UserTopic | None = (
                session.query(UserTopic)
                .filter(UserTopic.user_id == db_user.id, UserTopic.topic == text)
                .first()
            )
            if ut:
                session.delete(ut)
                session.flush()

                # Notify admin about topic removal
                notifier = get_notifier()
                if notifier:
                    await notifier.notify_user_activity(
                        username=user.username or str(user.id),
                        activity_type="topics_removed",
                        details={
                            "topic": text,
                            "total_count": session.query(UserTopic).filter(UserTopic.user_id == db_user.id).count()
                        }
                    )

                tracker = get_user_tracker()
                if tracker:
                    tracker.update_user_activity(db_user.id)

                await update.message.reply_text(
                    get_text('topic_removed', lang, topic=text),
                    reply_markup=get_topics_menu_keyboard(user.id)
                )
            else:
                await update.message.reply_text(
                    get_text('topic_not_found', lang, topic=text),
                    reply_markup=get_topics_menu_keyboard(user.id)
                )
            context.user_data.pop('removing_topics', None)
            
        elif context.user_data.get('removing_sources') and db_user:
            if db_user.sources:
                # Find the Source object by username
                source_to_remove = next((s for s in db_user.sources if s.username == text), None)
                if source_to_remove:
                    db_user.sources.remove(source_to_remove)
                    flag_modified(db_user, "sources")  # May not be needed for relationship, but safe
                    # Notify admin about source removal
                    notifier = get_notifier()
                    if notifier:
                        await notifier.notify_user_activity(
                            username=user.username or str(user.id),
                            activity_type="sources_removed",
                            details={
                                "source": text,
                                "total_count": len(db_user.sources)
                            }
                        )

                    tracker = get_user_tracker()
                    if tracker:
                        tracker.update_user_activity(db_user.id)
                    
                    await update.message.reply_text(
                        get_text('source_removed', lang, source=text),
                        reply_markup=get_sources_menu_keyboard(user.id)
                    )
                else:
                    await update.message.reply_text(
                        get_text('source_not_found', lang, source=text),
                        reply_markup=get_sources_menu_keyboard(user.id)
                    )
            context.user_data.pop('removing_sources', None)
    
    return CHOOSING_ACTION


async def view_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display user's current settings."""
    user = update.effective_user
    lang = get_user_language(user.id)
    
    with SessionLocal() as session:
        db_user = session.query(User).filter(User.telegram_id == user.id).first()
        
        if db_user:
            topics = [ut.topic for ut in db_user.user_topics] if db_user.user_topics else []
            sources = [s.username for s in db_user.sources] if db_user.sources else []
            
            topics_text = '\n• '.join(topics) if topics else "None"
            sources_text = '\n• '.join(sources) if sources else "None"
            
            time_until_next = get_time_until_next_summary(lang)
            
            language_display = "English" if lang == Language.ENGLISH else "Українська"
            
            settings_message = get_text('settings_message', lang, 
                topics_count=len(topics),
                topics=topics_text,
                sources_count=len(sources),
                sources=sources_text,
                time_remaining=time_until_next,
                lang_display=language_display
            )
            if not sources:
                settings_message += f"\n\n{get_text('settings_warning_no_sources', lang)}"
        else:
            settings_message = get_text('settings_not_found', lang)
    
    await update.message.reply_text(
        settings_message,
        reply_markup=get_main_menu_keyboard(user.id)
    )
    return CHOOSING_ACTION


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unknown commands."""
    try:
        user_id = update.effective_user.id if update.effective_user else None
        lang = get_user_language(user_id) if user_id else Language.ENGLISH
    except Exception:
        lang = Language.ENGLISH
    await update.message.reply_text(
        get_text('unknown_command', lang)
    )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors that occur in handlers."""
    logger.error(f"Update {update} caused error {context.error}")
    
    notifier = get_notifier()
    if notifier:
        error_details = {
            "update": str(update) if update else "None",
            "error_type": type(context.error).__name__,
            "error_message": str(context.error)
        }
        await notifier.notify_error("Bot Handler Error", str(context.error), error_details)
    
    if update and update.effective_message:
        try:
            # Try to get user language, fallback to English if not available
            try:
                user_id = update.effective_user.id if update.effective_user else None
                lang = get_user_language(user_id) if user_id else Language.ENGLISH
            except:
                lang = Language.ENGLISH
            
            await update.effective_message.reply_text(
                get_text('error_occurred', lang)
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")