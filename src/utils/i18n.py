from typing import Dict, Optional
from enum import Enum


class Language(Enum):
    """Supported languages."""
    UKRAINIAN = "uk"
    ENGLISH = "en"


TRANSLATIONS: Dict[str, Dict[str, str]] = {
    Language.ENGLISH.value: {
        # Summary labels
        "label_tldr": "TL;DR:",
        "label_sources": "Sources:",
        "label_themes": "Themes:",

        # Processing stats labels
        "stats_title": "🔍 Processing Statistics",
        "stats_messages_collected": "💬 Messages Collected:",
        "stats_messages_filtered": "🔬 Messages Filtered:",
        "stats_matched_topics_suffix": "matched {count} topics",
        "stats_sources_processed": "📡 Sources Processed:",
        "stats_time_saved": "⏰ Time Saved:",
        "stats_vs_manual": "vs manual reading",
        "stats_efficiency": "💡 Efficiency:",
        "stats_efficiency_suffix": "x faster than manual processing",

        # Duration units
        "duration_seconds": "seconds",
        "duration_minutes": "minutes",
        "duration_hours": "hours",

        # Welcome messages
        "welcome_message": (
            "👋 Hello {name}!\n\n"
            "I turn noisy Telegram into a clean, personalized brief.\n"
            "• ⏱️ Save time — I read channels for you and surface only what matters\n"
            "• 🧠 Stay focused — summaries are tailored to your topics\n"
            "• 📬 Be up to date — get a concise daily digest without endless scrolling\n\n"
            "You're in control: choose your topics and the sources to track.\n\n"
            "What would you like to do?"
        ),
        "help_title": "🤖 *Distill Help*",
        "help_features": "*Features:*",
        "help_how_it_works": "*How it works:*",
        
        # Features
        "feature_topics": "📝 *Topics Management* - Add/remove topics you're interested in (you can leave the topics empty and you'll get general summaries for specified sources)",
        "feature_sources": "📡 *Sources Management* - Add/remove sources to monitor (required)",
        "feature_summaries": "📊 *Auto Summaries*",
        
        # How it works
        "how_it_works_1": "1. Add topics you're interested in (e.g., 'OpenAI', 'LLM', 'Ethereum', 'Startup', 'vacancies')",
        "how_it_works_2": "2. Add public channels to monitor ",
        "how_it_works_3": "3. The bot will automatically send you summaries!",
        
        # Menu buttons
        "btn_start": "🚀 Start",
        "btn_help": "❓ Help",
        "btn_manage_topics": "📝 Manage Topics",
        "btn_manage_sources": "📡 Manage Sources", 
        "btn_view_settings": "⚙️ View Settings",
        "btn_testing": "🧪 Testing",
        "btn_add_topics": "➕ Add Topics",
        "btn_remove_topics": "➖ Remove Topics",
        "btn_view_topics": "📋 View Topics",
        "btn_add_sources": "➕ Add Sources",
        "btn_remove_sources": "➖ Remove Sources",
        "btn_view_sources": "📋 View Sources",
        "btn_back_main": "🔙 Back to Main Menu",
        "btn_back_topics": "🔙 Back to Topics Menu",
        "btn_back_sources": "🔙 Back to Sources Menu",
        "btn_run_collection": "🔄 Run Collection & Filtering",
        "btn_generate_summaries": "📊 Generate & Send Summaries",
        "btn_change_language": "🌐 Change Language",
        
        # Help footer
        "help_footer": "Use the menu buttons to navigate.",
        # General prompt
        "prompt_what_to_do": "What would you like to do?",
        
        # Topics management
        "topics_management_title": "📝 *Topics Management*",
        "topics_management_desc": (
            "Topics help me understand what content you're interested in.\n"
            "Examples: OpenAI, LLM, Ethereum, Startup, vacancies"
        ),
        "add_topics_title": "📝 *Add Topics*",
        "add_topics_prompt": (
            "Please enter the topics you're interested in, separated by commas.\n"
            "Example: OpenAI, LLM, Ethereum, Startup, vacancies\n\n"
            "Send your topics:"
        ),
        "topics_added_success": "✅ *Topics Added Successfully!*\n\nAdded topics: {topics}\n\nI'll now monitor content related to these topics.",
        "topics_limit_reached": "You have reached the limit of {limit} topics.",
        "topics_suffix_invalid": "⚠️ {count} invalid (too long or >7 words). Examples: {examples}",
        "topics_suffix_duplicates": "ℹ️ {count} duplicate(s) skipped",
        "topics_suffix_limit_reached": "⚠️ Limit reached; extra topics ignored",
        "topics_nothing_added": "No new topics were added (all were duplicates or over the limit).",
        "topics_already_exist": "ℹ️ All topics were already in your list.\n\nYour current topics: {topics}",
        "no_topics_to_remove": "📝 You don't have any topics to remove.",
        "remove_topics_title": "📝 *Remove Topics*\n\nSelect a topic to remove:",
        "topic_removed": "✅ Topic '{topic}' removed successfully!",
        "topic_not_found": "❌ Topic '{topic}' not found in your list.",
        "current_topics": "📝 *Your Current Topics:*\n\n• {topics}",
        "no_topics_added": "📝 *Your Topics*\n\nYou haven't added any topics yet.\nUse '➕ Add Topics' to get started!",
        
        # Sources management  
        "sources_management_title": "📡 *Sources Management*",
        "sources_management_desc": (
            "Sources are the public channels I should monitor.\n\n"
            "Examples: `@ai_meetups_ukraine`, `@oooneuro`, `@djinni_official`"
        ),
        "add_sources_title": "📡 *Add Sources*",
        "add_sources_prompt": (
            "Please enter the public channels you want to monitor.\n"
            "Each source should be on a new line.\n\n"
            "*Supported formats:*\n"
            "• @channelname\n"
            "• channelname\n" 
            "• https://t.me/channelname\n\n"
            "*Note:* Only public channels are supported.\n"
            "Groups, chats, megagroups, and private channels are not allowed.\n\n"
            "Send your sources:"
        ),
        "sources_validating": "🔍 Validating sources...\nThis may take a moment.",
        "sources_added_success": "✅ *{count} source(s) added successfully!*",
        "sources_already_exist": "ℹ️ *{count} source(s) already in your list:*",
        "sources_monitor_note": "\nI'll now monitor these sources for relevant content.",
        "sources_limit_reached": "You have reached the limit of {limit} sources.",
        "sources_limit_reached_suffix": "⚠️ Limit reached. Skipped {count} additional source(s).",
        "no_sources_to_remove": "📡 You don't have any sources to remove.",
        "remove_sources_title": "📡 *Remove Sources*\n\nSelect a source to remove:",
        "source_removed": "✅ Source '{source}' removed successfully!",
        "source_not_found": "❌ Source '{source}' not found in your list.",
        "current_sources": "📡 Your Current Sources:\n\n• {sources}",
        "no_sources_added": "📡 Your Sources\n\nYou haven't added any sources yet.\nUse '➕ Add Sources' to get started!",
        "validation_error": "❌ An error occurred during validation: {error}\n\nPlease try again later or contact support if the issue persists.",
        "sources_invalid_summary": "⚠️ {count} source(s) were invalid:",
        
        # Settings
        "settings_message": (
            "📝 Topics ({topics_count}):\n• {topics}\n\n"
            "📡 Sources ({sources_count}):\n• {sources}\n\n"
            "⏰ Next summary in: {time_remaining}\n"
            "🌐 Language: {lang_display}"
        ),
        "settings_warning_no_sources": "⚠️ You haven't added any sources yet. Without sources, no summaries will be generated.",
        "settings_not_found": "❌ User settings not found. Please use /start to initialize.",
        
        # Testing (admin only)
        "testing_menu_title": "🧪 *Testing Menu*",
        "testing_menu_desc": "You can manually run collection and filtering, or generate and send summaries.\nWhat would you like to do?",
        "access_denied": "❌ Access denied. Testing menu is only available for administrators.",
        "testing_access_denied": "❌ Access denied. Testing functions are only available for administrators.",
        "collection_starting": "🔄 Starting collection and filtering...\nThis may take a few minutes.",
        "collection_success": "✅ Collection and filtering completed successfully!",
        "collection_failed": "❌ Collection and filtering failed: {error}",
        "summaries_generating": "📊 Generating summaries...\nThis may take a few minutes.",
        "summaries_success": "✅ Summary generation completed!",
        "summaries_failed": "❌ Summary generation failed: {error}",
        "no_summaries_info": (
            "ℹ️ No summaries generated. This could mean:\n"
            "• No relevant messages found for your topics (topics can be too broad or too narrow)\n"
            "• Try adding more topics or sources\n\n"
            "💡 If you want you can leave the topics empty and you'll get general summaries for specified sources"
        ),
        
        # General messages
        "back_to_main": "🏠 Back to main menu. What would you like to do?",
        "unknown_command": "❓ I didn't understand that. Please use the menu buttons.",
        "operation_cancelled": "👋 Operation cancelled. Use /start to begin again!",
        "unknown_command_help": "❓ I don't understand that command. Use /help to see available commands or /start to access the menu.",
        "error_occurred": "⚠️ Sorry, something went wrong. Please try again or use /start to return to the main menu.",
        "user_not_found": "❌ User not found. Please use /start to initialize.",
        "user_not_found_db": "❌ User not found in database.",
        "provide_topics": "❌ Please provide some topics to add.",
        "provide_sources": "❌ Please provide some sources to add.",
        "no_valid_topics": "❌ No valid topics found. Please try again.",
        "nothing_interesting": "🥱 Today I didn't find anything interesting for you, you can try to add more topics or sources, if you want",
        
        # Language selection
        "language_changed": "✅ Language changed to English!",
        "select_language": "🌐 *Select Language*\n\nChoose your preferred language:",
        "btn_english": "🇺🇸 English",
        "btn_ukrainian": "🇺🇦 Українська",
    },
    
    Language.UKRAINIAN.value: {
        # Summary labels
        "label_tldr": "Коротко:",
        "label_sources": "Джерела:",
        "label_themes": "Теми:",

        # Processing stats labels
        "stats_title": "🔍 Статистика обробки",
        "stats_messages_collected": "💬 Зібрані повідомлення:",
        "stats_messages_filtered": "🔬 Відібрані повідомлення:",
        "stats_matched_topics_suffix": "відповідних тем: {count}",
        "stats_sources_processed": "📡 Опрацьовані джерела:",
        "stats_time_saved": "⏰ Зекономлено часу:",
        "stats_vs_manual": "порівняно з ручним читанням",
        "stats_efficiency": "💡 Ефективність:",
        "stats_efficiency_suffix": "x разів швидше, ніж ручна обробка",

        # Duration units
        "duration_seconds": "секунд",
        "duration_minutes": "хвилин",
        "duration_hours": "годин",

        # Welcome messages
        "welcome_message": (
            "👋 Привіт {name}!\n\n"
            "Я перетворюю шум Telegram на персоналізований корисний дайджест.\n"
            "• ⏱️ Економія часу — я читаю канали за вас і показую лише важливе\n"
            "• 🧠 Фокус на темах — підсумки підлаштовані під ваші інтереси\n"
            "• 📬 Завжди в курсі — стислий дайджест щодня о 18:00, без нескінченного скролу\n\n"
            "Ви керуєте всім: оберіть теми та джерела для відстеження.\n\n"
            "Що б ви хотіли зробити?"
        ),
        "help_title": "🤖 *Довідка Distill*",
        "help_features": "*Функції:*",
        "help_how_it_works": "*Як це працює:*",
        
        # Features
        "feature_topics": "📝 *Керування темами* - Додавати/видаляти теми, які вас цікавлять (якщо залишити теми порожніми, ви отримуватимете загальні підсумки для вказаних джерел)",
        "feature_sources": "📡 *Керування джерелами* - Додавати/видаляти джерела для моніторингу (обов'язково)",
        "feature_summaries": "📊 *Автоматичне отримання підсумків*",
        
        # How it works
        "how_it_works_1": "1. Додайте теми, які вас цікавлять (наприклад, 'вакансії', 'стартапи', 'OpenAI', 'LLM', 'Ethereum')",
        "how_it_works_2": "2. Додайте публічні канали для моніторингу",
        "how_it_works_3": "3. Бот автоматично надсилатиме вам підсумки щодня о 18:00",
        
        # Menu buttons
        "btn_start": "🚀 Почати",
        "btn_help": "❓ Допомога",
        "btn_manage_topics": "📝 Керувати темами",
        "btn_manage_sources": "📡 Керувати джерелами",
        "btn_view_settings": "⚙️ Переглянути налаштування",
        "btn_testing": "🧪 Тестування",
        "btn_add_topics": "➕ Додати теми",
        "btn_remove_topics": "➖ Видалити теми",
        "btn_view_topics": "📋 Переглянути теми",
        "btn_add_sources": "➕ Додати джерела",
        "btn_remove_sources": "➖ Видалити джерела",
        "btn_view_sources": "📋 Переглянути джерела",
        "btn_back_main": "🔙 Назад до головного меню",
        "btn_back_topics": "🔙 Назад до меню тем",
        "btn_back_sources": "🔙 Назад до меню джерел",
        "btn_run_collection": "🔄 Запустити збір та фільтрацію",
        "btn_generate_summaries": "📊 Згенерувати та надіслати підсумки",
        "btn_change_language": "🌐 Змінити мову",
        
        # Help footer
        "help_footer": "Використовуйте кнопки меню для навігації.",
        # General prompt
        "prompt_what_to_do": "Що б ви хотіли зробити?",
        
        # Topics management
        "topics_management_title": "📝 *Керування темами*",
        "topics_management_desc": (
            "Теми допомагають мені зрозуміти, який контент вас цікавить.\n"
            "Приклади: OpenAI, LLM, Ethereum, стартапи, вакансії"
        ),
        "add_topics_title": "📝 *Додати теми*",
        "add_topics_prompt": (
            "Будь ласка, введіть теми, які вас цікавлять, розділені комами.\n"
            "Приклад: OpenAI, LLM, Ethereum, стартапи, вакансії\n\n"
            "Надішліть ваші теми:"
        ),
        "topics_added_success": "✅ *Теми успішно додані!*\n\nДодані теми: {topics}\n\nТепер я буду відстежувати контент, пов'язаний з цими темами.",
        "topics_limit_reached": "Ви досягли ліміту у {limit} теми(тем).",
        "topics_suffix_invalid": "⚠️ {count} недійсних (надто довгі або більше 7 слів). Приклади: {examples}",
        "topics_suffix_duplicates": "ℹ️ Пропущено дублікати: {count}",
        "topics_suffix_limit_reached": "⚠️ Досягнуто ліміту; зайві теми проігноровано",
        "topics_nothing_added": "Нових тем не додано (усі були дублікатами або понад ліміт).",
        "topics_already_exist": "ℹ️ Усі теми вже є у вашому списку.\n\nВаші поточні теми: {topics}",
        "no_topics_to_remove": "📝 У вас немає тем для видалення.",
        "remove_topics_title": "📝 *Видалити теми*\n\nВиберіть тему для видалення:",
        "topic_removed": "✅ Тему '{topic}' успішно видалено!",
        "topic_not_found": "❌ Тему '{topic}' не знайдено у вашому списку.",
        "current_topics": "📝 *Ваші поточні теми:*\n\n• {topics}",
        "no_topics_added": "📝 *Ваші теми*\n\nВи ще не додали жодної теми.\nВикористайте '➕ Додати теми' для початку!",
        
        # Sources management
        "sources_management_title": "📡 *Керування джерелами*",
        "sources_management_desc": (
            "Джерела - це публічні канали, які я маю відстежувати.\n"
            "Приклади: `@ai_meetups_ukraine`, `@oooneuro`, `@djinni_official`"
        ),
        "add_sources_title": "📡 *Додати джерела*",
        "add_sources_prompt": (
            "Будь ласка, введіть публічні канали, які ви хочете відстежувати.\n"
            "Кожне джерело має бути на новому рядку.\n\n"
            "*Підтримувані формати:*\n"
            "• @channelname\n"
            "• channelname\n"
            "• https://t.me/channelname\n\n"
            "*Примітка:* Підтримуються лише публічні канали.\n"
            "Групи, чати, мегагрупи та приватні канали не дозволені.\n\n"
            "Надішліть ваші джерела:"
        ),
        "sources_validating": "🔍 Перевірка джерел...\nЦе може зайняти деякий час.",
        "sources_added_success": "✅ *{count} джерело(а) успішно додано!*",
        "sources_already_exist": "ℹ️ *{count} джерело(а) вже у вашому списку:*",
        "sources_monitor_note": "\nТепер я буду відстежувати ці джерела для відповідного контенту.",
        "sources_limit_reached": "Ви досягли ліміту у {limit} джерел(а).",
        "sources_limit_reached_suffix": "⚠️ Досягнуто ліміту. Пропущено додатково: {count} джерел(а).",
        "no_sources_to_remove": "📡 У вас немає джерел для видалення.",
        "remove_sources_title": "📡 *Видалити джерела*\n\nВиберіть джерело для видалення:",
        "source_removed": "✅ Джерело '{source}' успішно видалено!",
        "source_not_found": "❌ Джерело '{source}' не знайдено у вашому списку.",
        "current_sources": "📡 Ваші поточні джерела:\n\n• {sources}",
        "no_sources_added": "📡 Ваші джерела\n\nВи ще не додали жодного джерела.\nВикористайте '➕ Додати джерела' для початку!",
        "validation_error": "❌ Сталася помилка під час перевірки: {error}\n\nБудь ласка, спробуйте пізніше або зверніться до підтримки, якщо проблема не зникне.",
        "sources_invalid_summary": "⚠️ Недійсні джерела: {count}",
        
        # Settings
        "settings_message": (
            "📝 Теми ({topics_count}):\n• {topics}\n\n"
            "📡 Джерела ({sources_count}):\n• {sources}\n\n"
            "⏰ Наступний підсумок через: {time_remaining}\n"
            "🌐 Мова: {lang_display}"
        ),
        "settings_warning_no_sources": "⚠️ Ви ще не додали жодного джерела. Без джерел підсумки не будуть згенеровані.",
        "settings_not_found": "❌ Налаштування користувача не знайдено. Використайте /start для ініціалізації.",
        
        # Testing (admin only)
        "testing_menu_title": "🧪 *Меню тестування*",
        "testing_menu_desc": "Ви можете вручну запустити збір та фільтрацію або згенерувати та надіслати підсумки.\nЩо б ви хотіли зробити?",
        "access_denied": "❌ Доступ заборонено. Меню тестування доступне лише для адміністраторів.",
        "testing_access_denied": "❌ Доступ заборонено. Функції тестування доступні лише для адміністраторів.",
        "collection_starting": "🔄 Запуск збору та фільтрації...\nЦе може зайняти кілька хвилин.",
        "collection_success": "✅ Збір та фільтрацію успішно завершено!",
        "collection_failed": "❌ Збір та фільтрація не вдалися: {error}",
        "summaries_generating": "📊 Генерація підсумків...\nЦе може зайняти кілька хвилин.",
        "summaries_success": "✅ Генерацію підсумків завершено!",
        "summaries_failed": "❌ Генерація підсумків не вдалася: {error}",
        "no_summaries_info": (
            "ℹ️ Підсумки не згенеровано. Це може означати:\n"
            "• Не знайдено відповідних повідомлень для ваших тем\n"
            "• Спробуйте додати більше тем або джерел\n\n"
            "💡 Якщо ви хочете, ви можете залишити теми порожніми й ви отримуватимете загальні підсумки для вказаних джерел"
        ),
        
        # General messages
        "back_to_main": "🏠 Повернення до головного меню. Що б ви хотіли зробити?",
        "unknown_command": "❓ Я не зрозумів цього. Будь ласка, використовуйте кнопки меню.",
        "operation_cancelled": "👋 Операцію скасовано. Використайте /start, щоб почати знову!",
        "unknown_command_help": "❓ Я не розумію цієї команди. Використайте /help для перегляду доступних команд або /start для доступу до меню.",
        "error_occurred": "⚠️ Вибачте, щось пішло не так. Спробуйте ще раз або використайте /start для повернення до головного меню.",
        "user_not_found": "❌ Користувача не знайдено. Використайте /start для ініціалізації.",
        "user_not_found_db": "❌ Користувача не знайдено в базі даних.",
        "provide_topics": "❌ Будь ласка, надайте деякі теми для додавання.",
        "provide_sources": "❌ Будь ласка, надайте деякі джерела для додавання.",
        "no_valid_topics": "❌ Дійсних тем не знайдено. Спробуйте ще раз.",
        "nothing_interesting": "🥱 Сьогодні не знайшов нічого цікавого для вас, ви можете спробувати додати більше тем або джерел, якщо хочете",
        
        # Language selection
        "language_changed": "✅ Мову змінено на українську!",
        "select_language": "🌐 *Вибір мови*\n\nВиберіть бажану мову:",
        "btn_english": "🇺🇸 English",
        "btn_ukrainian": "🇺🇦 Українська",
    }
}


def detect_user_language(language_code: Optional[str]) -> Language:
    """
    Detect user's preferred language based on Telegram's language_code
    """
    if not language_code:
        return Language.ENGLISH
    
    primary_code = language_code.lower().split('-')[0]
    
    if primary_code == 'uk':
        return Language.UKRAINIAN
    else:
        return Language.ENGLISH


def get_text(key: str, language: Language, **kwargs) -> str:
    """
    Get translated text for a given key and language.
    
    Args:
        key: Translation key
        language: Target language
        **kwargs: Format arguments for the text
    
    Returns:
        Translated and formatted text
    """
    lang_code = language.value
    translations = TRANSLATIONS.get(lang_code, TRANSLATIONS[Language.ENGLISH.value])
    text = translations.get(key, f"[Missing: {key}]")
    
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    
    return text
