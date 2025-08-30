import os
import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple
import logging
import time

from telethon import TelegramClient
from telethon.tl.types import Channel
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from db.database import SessionLocal
from db.models import User, Message, Source
from db.qdrant_utils import ensure_collection, upsert_message_vectors
from utils.embedder import get_embeddings, get_embedding_dimension, get_embedder_info
from utils.text_utils import clean_text
from utils.stats_tracker import StatsTracker
from utils.user_tracker import get_user_tracker
from utils.datetime_utils import utc_now, to_utc

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TelegramCollector:
    """Collects messages from Telegram channels using Telethon"""
    
    def __init__(self):
        api_id_str = os.getenv("TELEGRAM_API_ID")
        self.api_hash = os.getenv("TELEGRAM_API_HASH")
        self.phone = os.getenv("TELEGRAM_PHONE")
        
        if not (api_id_str and self.api_hash and self.phone):
            raise ValueError("Missing required Telegram credentials. Set TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_PHONE in environment variables.")
        
        try:
            self.api_id = int(api_id_str)
        except (ValueError, TypeError):
            raise ValueError("TELEGRAM_API_ID must be a valid integer")
        
        self.session_name = os.getenv("TELEGRAM_SESSION_NAME", "collector_session")
        
        self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
        self.qdrant_collection_created = False
        
        try:
            embedder_info = get_embedder_info()
            logger.info(f"Using embedder: {embedder_info}")
        except Exception as e:
            logger.exception(f"Could not get embedder info: {e}")

    async def _ensure_qdrant_collection_async(self):
        if self.qdrant_collection_created:
            return
        try:
            dimension = get_embedding_dimension()
            if dimension:
                await ensure_collection("tg-summarizer", dimension)
                self.qdrant_collection_created = True
            else:
                raise ValueError("Could not determine embedding dimension.")
        except Exception as e:
            logger.exception("Failed to ensure Qdrant collection: %s", e)
    
    async def __aenter__(self):
        await self.authenticate()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client.is_connected():
            await self.client.disconnect()
            logger.info("Disconnected from Telegram")

    async def authenticate(self) -> bool:
        """Authenticate with Telegram"""
        if not self.phone:
            logger.error("Telegram phone number is not set.")
            return False
        try:
            await self.client.start(phone=self.phone)
            if not await self.client.is_user_authorized():
                logger.error("Failed to authenticate with Telegram")
                return False
            
            logger.info("Successfully authenticated with Telegram")
            return True
        except SessionPasswordNeededError:
            logger.error("2FA is enabled. Please handle 2FA authentication manually")
            return False
        except Exception as e:
            logger.exception(f"Authentication error: {e}")
            return False
    
    async def get_entity_info(self, source_username: str) -> Optional[Dict[str, Any]]:
        """Get entity information from source identifier"""
        try:
            entity = await self.client.get_entity(source_username)
            
            if isinstance(entity, Channel):
                info = {
                    "id": entity.id,
                    "title": entity.title,
                    "username": entity.username,
                    "type": "channel"
                }
                logger.info(f"✓ Found channel: {entity.title} (@{entity.username}) - ID: {entity.id}")
                return info
            else:
                logger.warning(f"Unsupported entity type for {source_username}: {type(entity)} - only channels are supported")
                return None
                
        except Exception as e:
            logger.exception(f"Failed to resolve Telegram entity for {source_username}: {e}")
            return None
    
    def _get_or_create_source(self, session: Session, entity_info: Dict[str, Any]) -> Source:
        """Get existing source or create new one"""
        source = session.query(Source).filter(Source.username == entity_info.get("username")).first()
        
        if not source:
            source = Source(
                title=entity_info.get("title"),
                username=entity_info.get("username"),
            )
            session.add(source)
            session.flush()
            logger.info(f"Created new source: {source.title} ({source.username})")
        else:
            if source.title != entity_info.get("title") or source.username != entity_info.get("username"):
                source.title = entity_info.get("title")
                source.username = entity_info.get("username")
                logger.info(f"Updated source info: {source.title} ({source.username})")
        
        return source
    
    async def collect_messages_from_source(
        self,
        source_username: str,
        limit: Optional[int] = None,
        offset_date: Optional[datetime] = None,
        min_date: Optional[datetime] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """Collect messages from a specific source with time filtering and return stats"""
        messages = []
        stats = {
            "messages_processed": 0,
            "messages_collected": 0,
            "skipped_empty": 0,
            "skipped_old": 0
        }
        
        try: 
            entity_info = await self.get_entity_info(source_username)
            if not entity_info:
                logger.error(f"Could not resolve entity for source: {source_username}")
                return messages, stats
            
            source_name = entity_info.get("title")
            
            async for message in self.client.iter_messages(
                source_username,
                limit=limit or 1000,
                offset_date=offset_date,
                reverse=False
            ):
                stats["messages_processed"] += 1
                
                # Normalize Telethon datetime to UTC-aware before comparisons
                msg_dt = message.date
                if msg_dt.tzinfo is None:
                    msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                else:
                    msg_dt = msg_dt.astimezone(timezone.utc)

                if min_date and msg_dt < min_date:
                    stats["skipped_old"] += 1
                    break
                
                if not message.text:
                    stats["skipped_empty"] += 1
                    continue
                
                
                message_data = {
                    "telegram_id": message.id,
                    "content": message.text,
                    "message_date": msg_dt,
                    "entity_info": entity_info,  # Only for source creation
                }
                
                messages.append(message_data)
                stats["messages_collected"] += 1
            
            logger.info(f"Collection summary for {source_name}:")
            logger.info(f"  - Total messages processed: {stats['messages_processed']}")
            logger.info(f"  - Messages collected: {stats['messages_collected']}")
            logger.info(f"  - Skipped (empty): {stats['skipped_empty']}")
            logger.info(f"  - Skipped (too old): {stats['skipped_old']}")
            
        except FloodWaitError as e:
            logger.warning(f"Rate limited for {e.seconds} seconds. Waiting...")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.exception(f"Error collecting messages from {source_name}: {e}")
        
        return messages, stats
    
    async def collect_messages_for_all_sources(
        self,
        days_back: int = 1,
        inactive_days_threshold: int = 7,
        limit_per_source: int = 50,
    ) -> Tuple[int, Dict[str, int]]:
        """Collect messages for all sources from active users."""
        user_tracker = get_user_tracker()
        if not user_tracker:
            logger.error("UserStatusTracker is not initialized.")
            return

        with SessionLocal() as session:
            users = session.query(User).all()
            threshold_date = utc_now() - timedelta(days=inactive_days_threshold)
            active_users = []
            for user in users:
                if user.telegram_id in getattr(user_tracker, 'blocked_users', set()):
                    continue
                last_seen = getattr(user_tracker, 'last_activity', {}).get(user.id)
                if not last_seen:
                    last_seen = user.created_at
                last_seen = to_utc(last_seen)
                if last_seen and last_seen < threshold_date:
                    continue
                active_users.append(user)

            source_set = {}
            for user in active_users:
                for source in user.sources:
                    if source.username:
                        source_set[source.username] = source
            sources = list(source_set.values())

        logger.info(f"Found {len(sources)} unique sources from active users.")
        now = utc_now()
        min_date = (now - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
        logger.info(f"Collecting messages from {len(sources)} sources since {min_date}.")

        total_new_messages: int = 0
        aggregate_stats: Dict[str, int] = {
            "messages_processed": 0,
            "messages_collected": 0,
            "skipped_empty": 0,
            "skipped_old": 0,
        }

        for i, source in enumerate(sources, 1):
            logger.info(f"[{i}/{len(sources)}] Processing source: {source.username}")
            try:
                source_start_time = time.time()
                messages, source_stats = await self.collect_messages_from_source(
                    source_username=source.username,
                    limit=limit_per_source,
                    min_date=min_date
                )
                new_messages: List[Message] = []
                if messages:
                    with SessionLocal.begin() as session:
                        new_messages = self._save_messages_to_db(session, messages)
                    if new_messages:
                        await self._upsert_message_embeddings_async(new_messages, source.username)
                source_elapsed_time = time.time() - source_start_time

                # Update per-user collection stats for this processed source
                # - messages_collected: number of new messages saved for this source
                # - messages_processed: total messages scanned for this source
                # - sources_processed: increment by 1 for each follower of this source
                new_count = len(new_messages)
                processed_count = source_stats.get("messages_processed", 0)
                # Update aggregates
                total_new_messages += new_count
                for key in aggregate_stats.keys():
                    aggregate_stats[key] += source_stats.get(key, 0)
                # Fetch fresh source with users in a new session
                with SessionLocal() as session:
                    db_source: Optional[Source] = (
                        session.query(Source).filter(Source.username == source.username).first()
                    )
                    if db_source and db_source.users:
                        followers_count = len(db_source.users)
                        per_user_collection_time = (
                            source_elapsed_time / followers_count if followers_count > 0 else 0.0
                        )
                        for follower in db_source.users:
                            tracker = StatsTracker(user_id=follower.id)
                            tracker.update_collection_stats(
                                messages_collected=new_count,
                                messages_processed=processed_count,
                                sources_processed=1,
                                collection_time=per_user_collection_time,
                            )
                if not messages:
                    logger.info(f"No new messages found for source {source.username}")
            except Exception as e:
                logger.exception(f"Failed to process source {source.username}: {e}")
                continue
        logger.info("Collection complete!")

        return total_new_messages, aggregate_stats

    def _save_messages_to_db(
        self, session: Session, messages: List[Dict[str, Any]]
    ) -> List[Message]:
        """Saves a list of messages to the database using a single batched INSERT.

        Rely on the unique constraint (source_id, telegram_id) to ignore duplicates.
        Uses SQLite ON CONFLICT DO NOTHING (equivalent to OR IGNORE) and RETURNING to
        fetch only newly inserted rows. Falls back to execute + query when RETURNING
        is not supported.
        """
        if not messages:
            return []

        # Resolve or create the Source once for this batch (all messages share the same source)
        entity_info = messages[0]["entity_info"]
        source = self._get_or_create_source(session, entity_info)

        rows = [
            {
                "source_id": source.id,
                "telegram_id": msg["telegram_id"],
                "content": msg["content"],
                "message_date": msg["message_date"],
            }
            for msg in messages
        ]

        inserted_messages: List[Message] = []
        stmt = sqlite_insert(Message).on_conflict_do_nothing(
            index_elements=[Message.__table__.c.source_id, Message.__table__.c.telegram_id]
        )

        try:
            # Prefer RETURNING to get only the rows that were actually inserted
            result = session.scalars(stmt.returning(Message), rows)
            inserted_messages = result.all()
            saved_count = len(inserted_messages)
        except SQLAlchemyError:
            # Fallback path when RETURNING is not supported by the SQLite library
            # Execute the batched insert with ON CONFLICT DO NOTHING
            session.execute(stmt, rows)
            session.flush()
            # Fetch all rows for these telegram_ids (includes pre-existing ones)
            telegram_ids = [r["telegram_id"] for r in rows]
            inserted_messages = (
                session.query(Message)
                .filter(
                    Message.source_id == source.id,
                    Message.telegram_id.in_(telegram_ids),
                )
                .all()
            )
            saved_count = len(inserted_messages)  # may include pre-existing

        duplicate_count = len(messages) - saved_count
        logger.info(
            f"Source @{source.username}: {saved_count} new messages saved, {duplicate_count} duplicates skipped."
        )
        return inserted_messages

    async def _upsert_message_embeddings_async(self, new_messages: List[Message], source_username: Optional[str] = None):
        """Generates and upserts embeddings for new messages asynchronously."""
        if not new_messages:
            return
        src_display = f"@{source_username}" if source_username else f"source_id={new_messages[0].source_id}"
        try:
            await self._ensure_qdrant_collection_async()
            valid_messages = []
            message_texts = []
            for message in new_messages:
                cleaned_text = clean_text(message.content)
                if cleaned_text and cleaned_text.strip():
                    valid_messages.append(message)
                    message_texts.append(cleaned_text)
            if not valid_messages:
                logger.warning(f"No valid messages with content found for {src_display}")
                return
            if len(valid_messages) != len(new_messages):
                logger.info(f"Filtered out {len(new_messages) - len(valid_messages)} empty messages for {src_display}")
            vectors = await asyncio.to_thread(get_embeddings, message_texts)
            if not vectors:
                logger.warning(f"No embeddings generated for {src_display}")
                return
            ids = [m.id for m in valid_messages]
            payloads = []
            for message in valid_messages:
                dt = message.message_date
                if dt is None:
                    ts = None
                else:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    ts = int(dt.timestamp())
                payloads.append({
                    "source_id": message.source_id,
                    "message_date_ts": ts if ts is not None else 0,
                })
            await upsert_message_vectors(ids, vectors, payloads)
            logger.info(f"Successfully upserted {len(valid_messages)} vectors for {src_display}")
        except Exception as e:
            logger.exception("Failed to upsert vectors to Qdrant for %s: %s", src_display, e)

async def run_collection():
    """Entrypoint for running the Telegram message collection pipeline."""
    logger.info(f"Starting run_collection")
    async with TelegramCollector() as collector:
        result = await collector.collect_messages_for_all_sources()
    logger.info("run_collection completed.")
    return result
