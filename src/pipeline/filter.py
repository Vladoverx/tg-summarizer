import asyncio
import argparse
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import selectinload

from db.database import SessionLocal
from db.models import FilteredMessage, Message, User, UserTopic
from db.qdrant_utils import get_qdrant_client
from qdrant_client.http import models as qmodels
from utils.embedder import get_embeddings
from utils.stats_tracker import track_filtering_time
from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


DEFAULT_TOP_K_PER_TOPIC = 30
DEFAULT_SCORE_THRESHOLD = 0.3


async def _filter_for_user(
    user: User,
    date_threshold: datetime,
    top_k_per_topic: int,
    score_threshold: float,
) -> Tuple[int, int]:
    """Filter messages for a single user based on their topics via Qdrant.

    Returns a tuple: (messages_filtered_count, unique_topics_matched)
    """
    if not user.user_topics:
        return 0, 0

    user_topics_list: List[UserTopic] = list(user.user_topics)
    topics: List[str] = [ut.topic for ut in user_topics_list]
    if not topics:
        return 0, 0

    if not user.sources:
        return 0, 0

    source_ids = [s.id for s in user.sources]
    if not source_ids:
        return 0, 0

    topic_to_vector: Dict[str, List[float]] = {}
    topics_needing_embeddings: List[str] = []
    for ut in user_topics_list:
        if ut.embedding:
            topic_to_vector[ut.topic] = ut.embedding
        else:
            topics_needing_embeddings.append(ut.topic)

    if topics_needing_embeddings:
        try:
            new_vectors = await asyncio.to_thread(get_embeddings, topics_needing_embeddings)
        except Exception as e:
            logger.exception(f"Failed to generate embeddings for user {user.id}: {e}")
            new_vectors = []

        if new_vectors:
            with SessionLocal.begin() as session:
                for topic, vec in zip(topics_needing_embeddings, new_vectors):
                    topic_to_vector[topic] = vec
                    ut = (
                        session.query(UserTopic)
                        .filter(UserTopic.user_id == user.id, UserTopic.topic == topic)
                        .first()
                    )
                    if ut:
                        ut.embedding = vec

    client = get_qdrant_client()

    messages_filtered = 0
    topics_with_hits: set[str] = set()

    payload_filter = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="source_id",
                match=qmodels.MatchAny(any=source_ids),
            )
        ]
    )

    for topic in topics:
        vector = topic_to_vector.get(topic)
        if not vector:
            continue
        try:
            results = await client.search(
                collection_name="tg-summarizer",
                query_vector=vector,
                limit=top_k_per_topic,
                with_payload=True,
                score_threshold=score_threshold,
                query_filter=payload_filter,
            )
        except Exception as e:
            logger.exception(f"Qdrant search failed for user {user.id}, topic '{topic}': {e}")
            continue

        if not results:
            continue

        with SessionLocal.begin() as session:
            for sp in results:
                try:
                    message_id = int(sp.id)
                except Exception:
                    continue

                msg: Optional[Message] = session.query(Message).options(selectinload(Message.source)).filter(Message.id == message_id).first()
                if not msg:
                    continue
                if msg.message_date and msg.message_date < date_threshold:
                    continue

                if msg.source_id not in source_ids:
                    continue

                exists = (
                    session.query(FilteredMessage)
                    .filter(
                        FilteredMessage.user_id == user.id,
                        FilteredMessage.message_id == msg.id,
                        FilteredMessage.topic == topic,
                    )
                    .first()
                )
                if exists:
                    continue

                fm = FilteredMessage(
                    user_id=user.id,
                    message_id=msg.id,
                    source_id=msg.source_id,
                    topic=topic,
                    content=msg.content,
                    message_date=msg.message_date,
                    similarity_score=float(sp.score) if sp.score is not None else 0.0,
                )
                session.add(fm)
                messages_filtered += 1
                topics_with_hits.add(topic)

    return messages_filtered, len(topics_with_hits)


async def filter_messages_async(
    user_id: Optional[int] = None,
    days_back: int = 1,
    top_k_per_topic: int = DEFAULT_TOP_K_PER_TOPIC,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
) -> Dict[str, int]:
    """Filter collected messages for users via Qdrant vector search.

    Args:
        user_id: If provided, process only this user; otherwise process all users with topics.
        days_back: Consider messages not older than this many days (midnight cutoff).
        top_k_per_topic: Maximum results to fetch per topic from vector search.
        score_threshold: Minimum similarity score to accept a match.

    Returns:
        Dict with aggregate counters: {"users_processed", "messages_filtered", "topics_matched"}
    """
    now = datetime.now()
    date_threshold = (now - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)

    with SessionLocal() as session:
        query = session.query(User).options(
            selectinload(User.sources),
            selectinload(User.user_topics),
        )
        if user_id is not None:
            query = query.filter(User.id == user_id)
        users: List[User] = query.all()

    users_processed = 0
    total_messages_filtered = 0
    total_topics_matched = 0

    for user in users:
        if not user.user_topics:
            continue

        users_processed += 1

        with track_filtering_time(user.id) as tracker:
            try:
                filtered_count, topics_matched = await _filter_for_user(
                    user=user,
                    date_threshold=date_threshold,
                    top_k_per_topic=top_k_per_topic,
                    score_threshold=score_threshold,
                )
            except Exception as e:
                logger.exception(f"Failed filtering for user {user.id}: {e}")
                filtered_count, topics_matched = 0, 0

            total_messages_filtered += filtered_count
            total_topics_matched += topics_matched

            tracker._filtering_stats = {  # type: ignore[attr-defined]
                "messages_filtered": filtered_count,
                "topics_matched": topics_matched,
            }

    logger.info(
        "Filtering completed: users=%d, messages_filtered=%d, topics_matched=%d",
        users_processed,
        total_messages_filtered,
        total_topics_matched,
    )

    return {
        "users_processed": users_processed,
        "messages_filtered": total_messages_filtered,
        "topics_matched": total_topics_matched,
    }


def _parse_args():
    parser = argparse.ArgumentParser(description="Run filtering on collected messages using Qdrant vector search")
    parser.add_argument("--user-id", type=int, default=None, help="Only filter for this user id")
    parser.add_argument("--days-back", type=int, default=1, help="Only consider messages from the last N days (default: 1)")
    parser.add_argument("--top-k-per-topic", type=int, default=DEFAULT_TOP_K_PER_TOPIC, help="Max Qdrant results per topic (default: 100)")
    parser.add_argument("--score-threshold", type=float, default=DEFAULT_SCORE_THRESHOLD, help="Min similarity score (default: 0.35)")
    return parser.parse_args()


def main():
    load_dotenv()
    args = _parse_args()
    logger.info(
        "Starting filtering run with params: user_id=%s, days_back=%d, top_k_per_topic=%d, score_threshold=%.2f",
        str(args.user_id), args.days_back, args.top_k_per_topic, args.score_threshold,
    )
    result = asyncio.run(
        filter_messages_async(
            user_id=args.user_id,
            days_back=args.days_back,
            top_k_per_topic=args.top_k_per_topic,
            score_threshold=args.score_threshold,
        )
    )
    logger.info("Filtering done: %s", result)


if __name__ == "__main__":
    main()


