from telegram import ReplyKeyboardMarkup
from utils.i18n import Language, get_text
from db.database import SessionLocal
from db.models import User


def get_user_language(user_id: int) -> Language:
    """Get user's preferred language from database."""
    with SessionLocal() as session:
        db_user = session.query(User).filter(User.telegram_id == user_id).first()
        if db_user and db_user.language:
            return Language(db_user.language)
        return Language.ENGLISH


def is_admin_user(user_id: int) -> bool:
    """Check if the user is an admin based on ADMIN_CHAT_ID."""
    import os
    admin_chat_id = os.getenv("ADMIN_CHAT_ID")
    if not admin_chat_id:
        return False
    try:
        return str(user_id) == str(admin_chat_id)
    except (ValueError, TypeError):
        return False


def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Get main menu keyboard based on user permissions."""
    lang = get_user_language(user_id)
    
    keyboard = [
        [get_text('btn_manage_sources', lang), get_text('btn_manage_topics', lang)],
        [get_text('btn_view_settings', lang), get_text('btn_change_language', lang)],
        [get_text('btn_help', lang)]
    ]
    
    # Add testing menu only for admin users
    if is_admin_user(user_id):
        keyboard.append([get_text('btn_testing', lang)])
    
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)


def get_testing_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Get testing menu keyboard."""
    lang = get_user_language(user_id)
    keyboard = [
        [get_text('btn_run_collection', lang), get_text('btn_generate_summaries', lang)],
        [get_text('btn_back_main', lang)]
    ]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)


def get_topics_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Get topics menu keyboard."""
    lang = get_user_language(user_id)
    keyboard = [
        [get_text('btn_add_topics', lang), get_text('btn_remove_topics', lang)],
        [get_text('btn_view_topics', lang), get_text('btn_back_main', lang)]
    ]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)


def get_sources_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Get sources menu keyboard."""
    lang = get_user_language(user_id)
    keyboard = [
        [get_text('btn_add_sources', lang), get_text('btn_remove_sources', lang)],
        [get_text('btn_view_sources', lang), get_text('btn_back_main', lang)]
    ]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)


def get_language_selection_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Get language selection keyboard."""
    lang = get_user_language(user_id)
    keyboard = [
        [get_text('btn_ukrainian', lang), get_text('btn_english', lang)],
        [get_text('btn_back_main', lang)]
    ]
    return ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)