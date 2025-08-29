import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from contextlib import contextmanager
import time

from db.database import SessionLocal
from db.models import ProcessingStats
from utils.i18n import Language, get_text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StatsTracker:
    """Tracks processing statistics for collection and filtering operations"""
    
    def __init__(self, user_id: int, date: Optional[datetime] = None):
        self.user_id = user_id
        base = date or datetime.now(timezone.utc)
        self.date = base.replace(hour=0, minute=0, second=0, microsecond=0)
        self.stats = {}
        
    def _get_or_create_stats(self, session) -> ProcessingStats:
        """Get or create ProcessingStats record for the user and date using the provided session."""
        stats = (
            session.query(ProcessingStats)
            .filter(ProcessingStats.user_id == self.user_id, ProcessingStats.date == self.date)
            .first()
        )
        if not stats:
            stats = ProcessingStats(
                user_id=self.user_id,
                date=self.date,
                messages_collected=0,
                messages_processed=0,
                sources_processed=0,
                messages_filtered=0,
                topics_matched=0,
                collection_time=0.0,
                filtering_time=0.0,
            )
            session.add(stats)
            session.flush()
        return stats
    
    def update_collection_stats(
        self,
        messages_collected: int = 0,
        messages_processed: int = 0,
        sources_processed: int = 0,
        collection_time: Optional[float] = None
    ):
        """Update collection statistics"""
        with SessionLocal.begin() as session:
            stats = (
                session.query(ProcessingStats)
                .filter(ProcessingStats.user_id == self.user_id, ProcessingStats.date == self.date)
                .first()
            )
            if not stats:
                stats = self._get_or_create_stats(session)

            stats.messages_collected += messages_collected
            stats.messages_processed += messages_processed
            stats.sources_processed += sources_processed
            
            if collection_time is not None:
                stats.collection_time = (stats.collection_time or 0) + collection_time
            
            logger.info(f"Updated collection stats for user {self.user_id}: "
                       f"collected={messages_collected}, processed={messages_processed}, "
                       f"sources={sources_processed}, time={collection_time:.2f}s" if collection_time is not None 
                       else f"collected={messages_collected}, processed={messages_processed}, sources={sources_processed}")
    
    def update_filtering_stats(
        self,
        messages_filtered: int = 0,
        topics_matched: int = 0,
        filtering_time: Optional[float] = None
    ):
        """Update filtering statistics"""
        with SessionLocal.begin() as session:
            stats = (
                session.query(ProcessingStats)
                .filter(ProcessingStats.user_id == self.user_id, ProcessingStats.date == self.date)
                .first()
            )
            if not stats:
                stats = self._get_or_create_stats(session)

            stats.messages_filtered += messages_filtered
            # Per-run additive is desired since flow runs once per day
            stats.topics_matched += topics_matched

            if filtering_time is not None:
                stats.filtering_time = (stats.filtering_time or 0) + filtering_time

            logger.info(
                f"Updated filtering stats for user {self.user_id}: "
                f"filtered={messages_filtered}, topics={topics_matched}, "
                f"time={filtering_time:.2f}s" if filtering_time is not None
                else f"filtered={messages_filtered}, topics={topics_matched}"
            )


@contextmanager
def track_collection_time(user_id: int, date: Optional[datetime] = None):
    """Context manager to track collection time"""
    tracker = StatsTracker(user_id, date)
    start_time = time.time()
    
    try:
        yield tracker
    finally:
        end_time = time.time()
        collection_time = end_time - start_time
        
        collection_stats = getattr(tracker, '_collection_stats', {})
        
        tracker.update_collection_stats(
            messages_collected=collection_stats.get('messages_collected', 0),
            messages_processed=collection_stats.get('messages_processed', 0),
            sources_processed=collection_stats.get('sources_processed', 0),
            collection_time=collection_time
        )
        logger.info(f"Collection completed for user {user_id} in {collection_time:.2f} seconds")


@contextmanager
def track_filtering_time(user_id: int, date: Optional[datetime] = None):
    """Context manager to track filtering time"""
    tracker = StatsTracker(user_id, date)
    start_time = time.time()
    
    try:
        yield tracker
    finally:
        end_time = time.time()
        filtering_time = end_time - start_time
        
        filtering_stats = getattr(tracker, '_filtering_stats', {})
        
        tracker.update_filtering_stats(
            messages_filtered=filtering_stats.get('messages_filtered', 0),
            topics_matched=filtering_stats.get('topics_matched', 0),
            filtering_time=filtering_time
        )
        logger.info(f"Filtering completed for user {user_id} in {filtering_time:.2f} seconds")


def get_user_stats(user_id: int, days_back: int = 1) -> Optional[ProcessingStats]:
    """Get the most recent processing statistics for a user"""
    target_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    with SessionLocal() as session:
        stats = session.query(ProcessingStats).filter(
            ProcessingStats.user_id == user_id,
            ProcessingStats.date == target_date
        ).first()
        
        return stats


def calculate_time_saved(stats: ProcessingStats) -> Dict[str, Any]:
    """Calculate estimated time saved based on processing statistics"""
    avg_words_per_message = 50
    reading_speed_wpm = 200
    manual_categorization_time = 3  # seconds per message
    
    total_messages_to_read = stats.messages_processed
    estimated_reading_time = (total_messages_to_read * avg_words_per_message) / reading_speed_wpm * 60  # in seconds
    estimated_categorization_time = total_messages_to_read * manual_categorization_time
    estimated_manual_time = estimated_reading_time + estimated_categorization_time
    
    actual_processing_time = (stats.collection_time or 0) + (stats.filtering_time or 0)
    
    time_saved = max(0, estimated_manual_time - actual_processing_time)
    
    efficiency_ratio = estimated_manual_time / actual_processing_time if actual_processing_time > 0 else 0
    
    return {
        "estimated_reading_time": estimated_reading_time,
        "estimated_categorization_time": estimated_categorization_time,
        "estimated_manual_time": estimated_manual_time,
        "actual_processing_time": actual_processing_time,
        "time_saved": time_saved,
        "efficiency_ratio": efficiency_ratio
    }


def format_time_duration(seconds: float, language: Language) -> str:
    """Format time duration in a human-readable format, localized."""
    if seconds < 60:
        unit = get_text("duration_seconds", language)
        return f"{seconds:.1f} {unit}"
    elif seconds < 3600:
        minutes = seconds / 60
        unit = get_text("duration_minutes", language)
        return f"{minutes:.1f} {unit}"
    else:
        hours = seconds / 3600
        unit = get_text("duration_hours", language)
        return f"{hours:.1f} {unit}"