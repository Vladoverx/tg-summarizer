import asyncio
import json
import logging
import os
import re
from typing import List, Optional, Dict, Any
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import selectinload

from google import genai
from google.genai import types

from db.database import SessionLocal
from db.models import User, FilteredMessage, Summary, Message
from utils.stats_tracker import get_user_stats, calculate_time_saved, format_time_duration
from utils.i18n import Language, get_text

# Configuration constants for processing
DEFAULT_BATCH_SIZE = 10  # Maximum number of users to process concurrently
DEFAULT_MESSAGE_CHUNK_SIZE = 50  # Number of messages to process in each chunk

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_gemini_client():
    """Get Gemini client using API key from environment"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is required")
    return genai.Client(api_key=api_key)


def get_user_language_preference(user_id: int) -> Language:
    """Get user's preferred language from database."""
    with SessionLocal() as session:
        db_user = session.query(User).filter(User.id == user_id).first()
        if db_user and db_user.language:
            return Language(db_user.language)
        return Language.ENGLISH


def get_language_instruction(language: Language) -> str:
    """Get language instruction for prompts based on user preference."""
    if language == Language.UKRAINIAN:
        return "Respond in Ukrainian language. Use Ukrainian text for all content including headlines, summaries, and bullet points."
    else:
        return "Respond in English language. Use English text for all content including headlines, summaries, and bullet points."


async def generate_summaries_async(
    user_id: Optional[int] = None,
    days_back: int = 1,
    min_messages_per_topic: int = 1,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    """
    Generate summaries for users based on their filtered messages with bounded concurrency.
    
    Args:
        user_id: Optional user ID to generate summaries for a specific user
        days_back: How many days back to look for messages (default: 1 day)
        min_messages_per_topic: Minimum messages needed per topic/source to generate summary
        batch_size: Maximum number of users to process concurrently (default: 10)
    """
    client = get_gemini_client()
    
    now = datetime.now(timezone.utc)
    date_threshold = (now - timedelta(days=days_back)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    
    total_successful = 0
    total_failed = 0
    total_processed = 0
    
    semaphore = asyncio.Semaphore(batch_size)

    async def run_for_user(user: User):
        async with semaphore:
            try:
                result = await _generate_summary_for_user(
                    client, user, date_threshold, min_messages_per_topic
                )
                return user.id, result, None
            except Exception as exc:  # _generate_summary_for_user already logs
                return user.id, None, exc

    try:
        with SessionLocal() as session:
            user_query = (
                session.query(User)
                .options(selectinload(User.sources), selectinload(User.user_topics))
            )
            if user_id:
                user_query = user_query.filter(User.id == user_id)
            
            running: set = set()

            for user in user_query.yield_per(DEFAULT_MESSAGE_CHUNK_SIZE):
                task = asyncio.create_task(run_for_user(user))
                running.add(task)
                if len(running) >= batch_size:
                    done, running = await asyncio.wait(
                        running, return_when=asyncio.FIRST_COMPLETED
                    )
                    for t in done:
                        uid, result, err = await t
                        total_processed += 1
                        if err is not None:
                            logger.error(
                                f"Failed to generate summary for user {uid}: {err}"
                            )
                            total_failed += 1
                        else:
                            total_successful += 1 if result else 0

            if running:
                done, _ = await asyncio.wait(running)
                for t in done:
                    uid, result, err = await t
                    total_processed += 1
                    if err is not None:
                        logger.error(f"Failed to generate summary for user {uid}: {err}")
                        total_failed += 1
                    else:
                        total_successful += 1 if result else 0

        logger.info(
            f"Summary generation completed: {total_successful} successful, {total_failed} failed out of {total_processed} total users"
        )
        
    except Exception as e:
        logger.exception(f"Critical error during summary generation: {e}")
        raise


def _filter_groups_by_min_size(
    groups: Dict[str, List[object]], min_size: int
) -> Dict[str, List[object]]:
    """Return only groups having at least min_size items."""
    return {key: items for key, items in groups.items() if len(items) >= min_size}


async def _generate_summary_for_user(
    client: genai.Client,
    user: User,
    date_threshold: datetime,
    min_messages_per_topic: int,
) -> Optional[str]:
    """Generate summary for a single user asynchronously"""
    try:
        user_stats = get_user_stats(user.id, days_back=1)
        time_analysis = calculate_time_saved(user_stats) if user_stats else None
        user_language = get_user_language_preference(user.id)

        if user.user_topics:
            # User has topics defined - use filtered messages approach
            logger.info(
                f"Generating topic-based summaries for user {user.id} with topics: {[ut.topic for ut in user.user_topics]}"
            )

            topic_messages = _get_filtered_messages_by_topic(user.id, date_threshold)

            if not topic_messages:
                logger.info(f"No recent filtered messages found for user {user.id}")
                return None

            relevant_topics = _filter_groups_by_min_size(
                topic_messages, min_messages_per_topic
            )

            if not relevant_topics:
                logger.info(
                    f"No topics with sufficient messages (min: {min_messages_per_topic}) "
                    f"for user {user.id}"
                )
                return None

            user_topics_list = [ut.topic for ut in user.user_topics]
            summary_content = await _generate_summary_async(
                client, relevant_topics, user_topics_list, user_language, user_stats, time_analysis
            )
            
            if summary_content and "no relevant updates" not in summary_content.lower():
                _save_summary(user.id, relevant_topics, summary_content, is_topic_based=True)
                topics_list = list(relevant_topics.keys())
                logger.info(f"Generated topic-based summary for user {user.id} covering topics: {topics_list}")
                return summary_content
            else:
                logger.info(f"No relevant topic-based content found for user {user.id}")
                return None
        else:
            # User has no topics defined - use raw messages approach
            logger.info(f"Generating source-based summaries for user {user.id} (no topics defined)")

            source_messages = _get_raw_messages_by_source(user.id, date_threshold)

            if not source_messages:
                logger.info(f"No recent raw messages found for user {user.id}")
                return None

            relevant_sources = _filter_groups_by_min_size(
                source_messages, min_messages_per_topic
            )

            if not relevant_sources:
                logger.info(
                    f"No sources with sufficient messages (min: {min_messages_per_topic}) "
                    f"for user {user.id}"
                )
                return None

            summary_content = await _generate_summary_without_topics_async(client, relevant_sources, user_language, user_stats, time_analysis)
            
            if summary_content and "no relevant updates" not in summary_content.lower():
                _save_summary(user.id, relevant_sources, summary_content, is_topic_based=False)
                sources_list = list(relevant_sources.keys())
                logger.info(f"Generated source-based summary for user {user.id} covering sources: {sources_list}")
                return summary_content
            else:
                logger.info(f"No relevant source-based content found for user {user.id}")
                return None
            
    except Exception as e:
        logger.exception(f"Failed to generate summary for user {user.id}: {e}")
        raise


def _get_filtered_messages_by_topic(
    user_id: int, 
    date_threshold: datetime, 
) -> Dict[str, List[FilteredMessage]]:
    """
    Get filtered messages grouped by topic for a user within the date threshold.
    """
    with SessionLocal() as session:
        filtered_messages = (
            session.query(FilteredMessage)
            .options(selectinload(FilteredMessage.source))
            .filter(
                FilteredMessage.user_id == user_id,
                FilteredMessage.message_date >= date_threshold
            )
            .order_by(FilteredMessage.similarity_score.desc(), FilteredMessage.message_date.desc())
            .yield_per(DEFAULT_MESSAGE_CHUNK_SIZE)
        )

        topic_messages: Dict[str, List[FilteredMessage]] = defaultdict(list)
        for msg in filtered_messages:
            topic_messages[msg.topic].append(msg)

        return dict(topic_messages)


def _get_raw_messages_by_source(
    user_id: int, 
    date_threshold: datetime,
    limit_per_source: int = 100
) -> Dict[str, List[Message]]:
    """
    Get raw messages grouped by source for users without topics within the date threshold.
    """
    with SessionLocal() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user or not user.sources:
            return {}
        
        user_source_ids = [source.id for source in user.sources]
        source_messages: Dict[str, List[Message]] = defaultdict(list)
        
        for msg in session.query(Message).options(
            selectinload(Message.source)
        ).filter(
            Message.source_id.in_(user_source_ids),
            Message.message_date >= date_threshold
        ).order_by(Message.message_date.desc()).yield_per(DEFAULT_MESSAGE_CHUNK_SIZE):  # Process messages in chunks
            
            source_key = msg.source.username if msg.source and msg.source.username else str(msg.source_id)
            
            if len(source_messages[source_key]) < limit_per_source:
                source_messages[source_key].append(msg)
        
        return dict(source_messages)


def _save_summary(user_id: int, relevant_data: Dict, summary_content: str, is_topic_based: bool = True) -> None:
    """Save summary to database synchronously"""
    with SessionLocal.begin() as session:
        data_list = list(relevant_data.keys())
        
        if is_topic_based:
            # Topic-based summary
            title = f"Daily Summary: {', '.join(data_list)}"
            topic = ', '.join(data_list)
        else:
            # Source-based summary
            title = f"Daily Summary from Sources: {', '.join(data_list)}"
            topic = f"Sources: {', '.join(data_list)}"
        
        summary = Summary(
            user_id=user_id,
            title=title,
            content=summary_content,
            topic=topic,
        )
        session.add(summary)


def _build_topic_prompt(messages_data, user_language, extra_context):
    user_topics: List[str] = extra_context["user_topics"]
    topics_list = list(messages_data.keys())
    language_instruction = get_language_instruction(user_language)
    lines: List[str] = []
    for topic, messages in messages_data.items():
        lines.append(f"\n## TOPIC: {topic}\n")
        for i, msg in enumerate(messages, 1):
            source_name = (
                msg.source.username if msg.source and msg.source.username else f"Source {msg.source_id}"
            )
            lines.append(f"\n{i}. From [{source_name}] (Score: {msg.similarity_score:.3f})\n")
            lines.append(f"   Date: {msg.message_date}\n")
            lines.append(f"   Content: {msg.content}\n")
    all_messages_text = "".join(lines)
    return f"""You are an engaging news curator. Analyze the messages and create captivating summaries for relevant topics.

{language_instruction}

USER'S INTERESTS: {list(user_topics)}

TOPICS WITH MESSAGES: {topics_list}

MESSAGES:
{all_messages_text}

INSTRUCTIONS:

1. OVERALL SUMMARY:
   - Create a compelling main headline capturing the most significant development across all topics
   - Headline MUST include at least one relevant emoji
   - Write a 2-3 sentence TL;DR that synthesizes the essence of all major news
   - TL;DR MUST include at least one relevant emoji

2. TOPIC-SPECIFIC CONTENT:
   - Evaluate if there's truly valuable, non-redundant information matching user's interests
   - For each relevant topic with meaningful updates:
     - Write a brief, vivid paragraph (1-2 sentences) in journalistic style, focusing on key developments
     - The brief MUST include at least one relevant emoji
     - List 3-5 key points as concise bullets with unique insights
     - Each bullet MUST include at least one relevant emoji

3. QUALITY FILTERS:
   - Be selective: ignore low-value, repetitive, or off-topic content
   - Only include topics with substantive, non-redundant content
   - If nothing relevant or engaging, set is_relevant to false and topic_summaries to empty array

STYLE:
- Keep it concise and exciting
 - Include at least one emoji in EVERY section (headline, TL;DR, each topic brief, and each bullet)
 - Distribute emojis evenly across sections; avoid clustering many emojis in one section and none in others
 - Prefer 1 emoji per sentence/bullet (max 2 if it truly improves clarity)
 - Avoid repeating the same emoji; choose context-appropriate emojis

Respond strictly as JSON matching the schema."""


def _format_stats_block(user_stats, time_analysis, mode: str, user_language: Language) -> List[str]:
    """Build shared statistics block based on mode ('topic' or 'source'), localized."""
    if not (user_stats and time_analysis):
        return []
    parts: List[str] = [
        f"<b>{get_text('stats_title', user_language)}</b>",
    ]
    if hasattr(user_stats, "messages_collected"):
        parts.append(
            f"<b>{get_text('stats_messages_collected', user_language)}</b> "
            + str(user_stats.messages_collected)
        )
    if mode == "topic" and hasattr(user_stats, "messages_filtered"):
        matched = getattr(user_stats, "topics_matched", 0)
        parts.append(
            f"<b>{get_text('stats_messages_filtered', user_language)}</b> "
            + f"{user_stats.messages_filtered} ("
            + get_text('stats_matched_topics_suffix', user_language, count=matched)
            + ")"
        )
    if mode == "source" and hasattr(user_stats, "sources_processed"):
        parts.append(
            f"<b>{get_text('stats_sources_processed', user_language)}</b> "
            + str(user_stats.sources_processed)
        )
    if time_analysis.get("time_saved", 0) > 0:
        parts.append(
            f"<b>{get_text('stats_time_saved', user_language)}</b> "
            + f"~{format_time_duration(time_analysis['time_saved'], user_language)} ("
            + get_text('stats_vs_manual', user_language)
            + ")"
        )
        parts.append(
            f"<b>{get_text('stats_efficiency', user_language)}</b> "
            + f" {time_analysis['efficiency_ratio']:.1f}"
            + get_text('stats_efficiency_suffix', user_language)
        )
    parts.append("")
    return parts


def _normalize_at_username(value: Optional[str]) -> Optional[str]:
    """Return a normalized @username or None if not available."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    return f"@{text.lstrip('@')}"


def _collect_usernames_from_messages(messages: List[FilteredMessage]) -> List[str]:
    """Collect unique @usernames from message.sources preserving order."""
    seen: set[str] = set()
    ordered_usernames: List[str] = []
    for message in messages:
        try:
            raw_username = getattr(getattr(message, "source", None), "username", None)
            normalized = _normalize_at_username(raw_username)
            if normalized and normalized not in seen:
                seen.add(normalized)
                ordered_usernames.append(normalized)
        except Exception:
            continue
    return ordered_usernames


def _build_topic_to_usernames(messages_data: Dict[str, List[FilteredMessage]]) -> Dict[str, List[str]]:
    """Build mapping topic -> ordered unique @usernames extracted from messages."""
    return {topic_key: _collect_usernames_from_messages(msgs) for topic_key, msgs in messages_data.items()}


def _find_key_case_insensitive(candidates: Dict[str, Any], query: str) -> Optional[str]:
    """Return exact key from candidates matching query case-insensitively, or None."""
    q = str(query)
    for key in candidates.keys():
        if str(key).lower() == q.lower():
            return key
    return None


def _format_topic_result(result, messages_data, user_language, extra_context):
    user_stats = extra_context.get("user_stats")
    time_analysis = extra_context.get("time_analysis")
    topics_list = list(messages_data.keys())
    topic_to_usernames: Dict[str, List[str]] = _build_topic_to_usernames(messages_data)
    if result.get("is_relevant", False) and result.get("topic_summaries"):
        summary_parts = []
        if result.get("overall_headline"):
            summary_parts.append(f"<b>{result['overall_headline']}</b>\n")
        if result.get("tldr"):
            summary_parts.append(
                f"<b>{get_text('label_tldr', user_language)}</b>\n {result['tldr']}\n"
            )
        for ts in result["topic_summaries"]:
            summary_parts.append(f"<u><i>{ts['topic']}</i></u>")
            if ts.get("brief"):
                summary_parts.append(f"{ts['brief']}\n")
            if ts.get("key_points"):
                for point in ts["key_points"]:
                    summary_parts.append(f"• {point}\n")
            topic_name = str(ts.get("topic", ""))
            matched_topic_key = (
                topic_name
                if topic_name in topic_to_usernames
                else _find_key_case_insensitive(topic_to_usernames, topic_name)
            )
            usernames_for_topic = topic_to_usernames.get(matched_topic_key or "", [])
            if usernames_for_topic:
                sources_text = ", ".join(usernames_for_topic)
                summary_parts.append(
                    f"<b>{get_text('label_sources', user_language)}</b> {sources_text}\n"
                )
            summary_parts.append("")
        summary_parts.extend(
            _format_stats_block(user_stats, time_analysis, mode="topic", user_language=user_language)
        )
        return "\n".join(summary_parts)
    else:
        escaped_topics = ", ".join(t for t in topics_list)
        if user_language == Language.UKRAINIAN:
            return f"Сьогодні не знайдено відповідних оновлень для тем: {escaped_topics}."
        else:
            return f"No relevant updates found for topics: {escaped_topics} today."


def _build_source_prompt(messages_data, user_language, extra_context):
    language_instruction = get_language_instruction(user_language)
    lines: List[str] = []
    for source_key, messages in messages_data.items():
        lines.append(f"\n## SOURCE: {source_key}\n")
        for msg in messages:
            lines.append(f"   Date: {msg.message_date}\n")
            lines.append(f"   Content: {msg.content}\n")
    all_messages_text = "".join(lines)
    return f"""You are an expert news curator and deduplication specialist. Analyze messages from various Telegram sources to create a comprehensive, non-redundant news summary.

{language_instruction}

MESSAGES:
{all_messages_text}

INSTRUCTIONS:

1. DEDUPLICATION STRATEGY:
   - Identify all news stories/topics mentioned across sources
   - For each story, determine which source provides the BEST coverage (most detailed, authoritative, or comprehensive)
   - Assign each news item to only ONE source - the one with superior coverage
   - Remove redundant coverage from other sources entirely

2. OVERALL SUMMARY:
   - Create a compelling main headline capturing the most significant development
   - Headline MUST include at least one relevant emoji
   - Write a 2-3 sentence TL;DR that synthesizes the essence of all major news
   - TL;DR MUST include at least one relevant emoji

3. SOURCE-SPECIFIC CONTENT:
   - For each source, include ONLY unique content not covered better elsewhere
   - Write brief paragraphs focusing exclusively on this source's unique contributions
   - The brief MUST include at least one relevant emoji
   - List 3-5 key points that are exclusive to this source (no repetition across sources)
   - Each bullet MUST include at least one relevant emoji
   - Identify themes unique to this source's coverage angle
   - Themes MUST NOT include emojis; use plain-text keywords only
   - Use emojis to add emphasis or categorization when it improves clarity. Avoid repetition.

4. QUALITY FILTERS:
   - Ignore low-value, repetitive, spam, or trivial content
   - Only include sources with substantive, unique contributions
   - If a source has no unique value after deduplication, exclude it entirely
   - Prioritize newsworthy, engaging content

5. CONTENT ASSIGNMENT RULES:
   - Breaking news → assign to the source that reported it first or most comprehensively
   - Analysis/opinion → assign to the source with the most insightful take
   - Updates → assign to the source with the most recent or detailed information
   - Context/background → assign to the source providing the best context

Focus on creating a cohesive, non-redundant news digest where each source adds unique value.

STYLE:
- Keep it professional yet lively
 - Include at least one emoji in EVERY section (headline, TL;DR, each source brief, and each bullet)
 - Distribute emojis evenly across sections; avoid clustering many emojis in one section and none in others
 - Prefer 1 emoji per sentence/bullet (max 2 if it truly improves clarity)
 - Avoid repeating the same emoji; choose context-appropriate emojis
 - Do NOT use emojis in themes

Respond strictly as JSON matching the provided schema."""


def _format_source_result(result, messages_data, user_language, extra_context):
    user_stats = extra_context.get("user_stats")
    time_analysis = extra_context.get("time_analysis")
    sources_list = list(messages_data.keys())
    source_display_map: Dict[str, str] = {}
    for source_key, msgs in messages_data.items():
        display = None
        if msgs:
            try:
                uname = getattr(getattr(msgs[0], "source", None), "username", None)
                if uname:
                    display = f"@{uname.lstrip('@')}"
            except Exception:
                pass
        if not display and isinstance(source_key, str):
            # If key itself looks like a username, normalize it
            if source_key.strip():
                display = f"@{source_key.lstrip('@')}"
        if not display:
            display = str(source_key)
        source_display_map[str(source_key)] = display
    
    def _normalize_source_key(value: str) -> str:
        text = str(value or "").strip()
        text = text.lstrip('@')
        # remove non-alphanumeric to make underscores/dots/hyphens equivalent
        return re.sub(r"[^a-zA-Z0-9]", "", text).lower()

    def _find_source_key_match(candidates: Dict[str, str], query: str) -> Optional[str]:
        # exact match first
        if query in candidates:
            return query
        qn = _normalize_source_key(query)
        for key in candidates.keys():
            if _normalize_source_key(key) == qn:
                return key
        return None
    if result.get("source_summaries"):
        summary_parts = []
        if result.get("overall_headline"):
            summary_parts.append(f"<b>{result['overall_headline']}</b>\n")
        if result.get("tldr"):
            summary_parts.append(
                f"<b>{get_text('label_tldr', user_language)}</b>\n {result['tldr']}\n"
            )
        for ss in result["source_summaries"]:
            raw_source = str(ss.get("source", ""))
            matched_key = _find_source_key_match(source_display_map, raw_source)
            display_source = (
                source_display_map.get(matched_key) if matched_key is not None else f"@{raw_source.lstrip('@')}"
            )
            summary_parts.append(f"{display_source}")
            if ss.get("brief"):
                summary_parts.append(f"{ss['brief']}\n")
            if ss.get("key_points"):
                for point in ss["key_points"]:
                    summary_parts.append(f"• {point}")
            if ss.get("themes"):
                themes_text = ", ".join(t for t in ss["themes"]) 
                summary_parts.append(
                    f"\n<b>{get_text('label_themes', user_language)}</b> {themes_text}\n"
                )
            summary_parts.append("")
        summary_parts.extend(
            _format_stats_block(user_stats, time_analysis, mode="source", user_language=user_language)
        )
        return "\n".join(summary_parts)
    else:
        escaped_sources = ", ".join(s for s in sources_list)
        if user_language == Language.UKRAINIAN:
            return f"Сьогодні не знайдено відповідних оновлень з джерел: {escaped_sources}."
        else:
            return f"No relevant updates found from sources: {escaped_sources} today."


async def _generate_summary_generic(
    client,
    messages_data,
    user_language,
    response_schema,
    prompt_builder,
    result_formatter,
    extra_context=None,
):
    prompt = prompt_builder(messages_data, user_language, extra_context)
    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0.5,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
            ),
        )
        if not response.text:
            raise ValueError("Empty response from Gemini API")
        result = json.loads(response.text)
        return result_formatter(result, messages_data, user_language, extra_context)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {e}")
        logger.error(f"Raw response: {getattr(response, 'text', None)}")
        raise ValueError(f"Failed to parse JSON response: {e}")
    except Exception as e:
        logger.exception(f"Gemini API error: {e}")
        raise


async def _generate_summary_async(
    client: genai.Client, 
    relevant_topics: Dict[str, List[FilteredMessage]],
    user_topics: List[str],
    user_language: Language,
    user_stats: Optional[object] = None,
    time_analysis: Optional[Dict] = None
) -> str:
    response_schema = {
        "type": "object",
        "properties": {
            "overall_headline": {
                "type": "string",
                "description": "Compelling main headline that captures the most significant news across all topics"
            },
            "tldr": {
                "type": "string",
                "description": "Concise 2-3 sentence summary capturing the essence of all major developments"
            },
            "is_relevant": {
                "type": "boolean",
                "description": "Whether there is truly valuable, non-redundant information matching any user interests"
            },
            "topic_summaries": {
                "type": "array",
                "description": "Array of summaries for each relevant topic (empty if not relevant)",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "brief": {
                            "type": "string",
                            "description": "Concise, engaging paragraph (1-2 sentences) in journalistic style, focusing on key developments without redundancy"
                        },
                        "key_points": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "3-5 concise bullet points with unique insights or takeaways (avoid repetition)"
                        },
                        "sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Sources referenced"
                        }
                    },
                    "required": ["topic", "brief", "key_points", "sources"]
                }
            }
        },
        "required": ["overall_headline", "tldr", "is_relevant", "topic_summaries"]
    }
    extra_context = {"user_topics": user_topics, "user_stats": user_stats, "time_analysis": time_analysis}
    return await _generate_summary_generic(
        client,
        relevant_topics,
        user_language,
        response_schema,
        _build_topic_prompt,
        _format_topic_result,
        extra_context,
    )


async def _generate_summary_without_topics_async(
    client: genai.Client, 
    relevant_sources: Dict[str, List[Message]],
    user_language: Language,
    user_stats: Optional[object] = None,
    time_analysis: Optional[Dict] = None
) -> str:
    response_schema = {
        "type": "object",
        "properties": {
            "overall_headline": {
                "type": "string",
                "description": "Compelling main headline that captures the most significant news across all sources"
            },
            "tldr": {
                "type": "string",
                "description": "Concise 2-3 sentence summary capturing the essence of all major developments"
            },
            "source_summaries": {
                "type": "array",
                "description": "Array of summaries for each source with unique, non-duplicated content",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "brief": {
                            "type": "string",
                            "description": "Concise paragraph focusing on unique content from this source only"
                        },
                        "key_points": {
                            "type": "array",
                            "description": "3-5 unique insights exclusive to this source (no duplication across sources)",
                            "items": {"type": "string"}
                        },
                        "themes": {
                            "type": "array",
                            "description": "2-3 main themes unique to this source's coverage",
                            "items": {"type": "string"}
                        }
                    },
                    "required": ["source", "brief", "key_points", "themes"]
                }
            }
        },
        "required": ["overall_headline", "tldr", "source_summaries"]
    }
    extra_context = {"user_stats": user_stats, "time_analysis": time_analysis}
    return await _generate_summary_generic(
        client,
        relevant_sources,
        user_language,
        response_schema,
        _build_source_prompt,
        _format_source_result,
        extra_context,
    )


def get_user_summaries(
    user_id: int,
    days_back: int = 7,
    topic: Optional[str] = None
) -> List[Summary]:
    """
    Get user summaries.
    """
    with SessionLocal() as session:
        now = datetime.now(timezone.utc)
        date_threshold = (now - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        query = (
            session.query(Summary)
            .filter(
                Summary.user_id == user_id,
                Summary.created_at >= date_threshold
            )
            .order_by(Summary.created_at.desc())
        )
        
        if topic:
            query = query.filter(Summary.topic == topic)
            
        return query.all()
