from __future__ import annotations

from typing import List, Dict, Any
import os
import logging
from datetime import datetime, timedelta

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from db.database import SessionLocal
from db.models import Message

logger = logging.getLogger(__name__)

_qdrant_client: AsyncQdrantClient | None = None


def _create_client() -> AsyncQdrantClient:
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")

    if url:
        logger.info("Connecting to remote Qdrant instance at %s", url)
        return AsyncQdrantClient(url=url, api_key=api_key)

    raise ValueError("No QDRANT_URL provided")


def get_qdrant_client() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = _create_client()
    return _qdrant_client


async def ensure_collection(collection_name: str, vector_size: int) -> None:
    client = get_qdrant_client()
    try:
        if await client.collection_exists(collection_name):
            await ensure_payload_indexes(collection_name)
            return

        logger.info("Creating Qdrant collection '%s' (dim=%d)...", collection_name, vector_size)
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
        )
        
        await ensure_payload_indexes(collection_name)
    except Exception as e:
        logger.exception(f"Failed to ensure Qdrant collection '{collection_name}': {e}")
        raise


async def ensure_payload_indexes(collection_name: str) -> None:
    client = get_qdrant_client()
    
    try:
        await client.create_payload_index(
            collection_name=collection_name,
            field_name="source_id",
            field_schema=qmodels.PayloadSchemaType.INTEGER,
        )
        logger.info("Created payload index for 'source_id' field in collection '%s'", collection_name)
    except Exception as e:
        logger.exception("Could not create source_id index (may already exist): %s", e)
    
    try:
        await client.create_payload_index(
            collection_name=collection_name,
            field_name="source",
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
        logger.info("Created payload index for 'source' field in collection '%s'", collection_name)
    except Exception as e:
        logger.exception("Could not create source index (may already exist): %s", e)


async def upsert_message_vectors(
    message_ids: List[int],
    vectors: List[List[float]],
    payloads: List[Dict[str, Any]] | None = None,
    collection_name: str = "tg-summarizer",
) -> None:
    if not message_ids:
        return

    client = get_qdrant_client()

    if payloads is None:
        payloads = [{} for _ in message_ids]

    await client.upsert(
        collection_name=collection_name,
        points=[
            qmodels.PointStruct(id=m_id, vector=vec, payload=pld)
            for m_id, vec, pld in zip(message_ids, vectors, payloads)
        ],
        wait=True,
    )

    logger.info("Upserted %d vectors into Qdrant collection '%s'", len(message_ids), collection_name) 

async def cleanup_old_vectors(
    collection_name: str = "tg-summarizer",
    days_to_keep: int = 30,
    dry_run: bool = False
) -> int:
    """
    Remove vectors for messages older than specified days.
    
    Args:
        collection_name: Qdrant collection name
        days_to_keep: Number of days to keep vectors (default: 30)
        dry_run: If True, only count what would be deleted
    
    Returns:
        Number of vectors deleted (or would be deleted if dry_run=True)
    """
    client = get_qdrant_client()
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    with SessionLocal() as session:
        old_message_ids = session.query(Message.id).filter(
            Message.message_date < cutoff_date
        ).all()
        
        old_ids = [msg_id[0] for msg_id in old_message_ids]
    
    if not old_ids:
        logger.info("No old vectors to cleanup")
        return 0
    
    if dry_run:
        logger.info(f"Would delete {len(old_ids)} vectors older than {cutoff_date}")
        return len(old_ids)
    
    await client.delete(
        collection_name=collection_name,
        points_selector=qmodels.PointIdsList(points=old_ids),
        wait=True,
    )
    
    logger.info(f"Cleaned up {len(old_ids)} old vectors from collection '{collection_name}'")
    return len(old_ids)