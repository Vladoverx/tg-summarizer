import os
import logging
from typing import List, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

_openai_client: Optional[OpenAI] = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings")
        logger.info("Initializing OpenAI client")
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
        logger.info("OpenAI client initialized successfully")
    return _openai_client


def get_embeddings(texts: List[str]) -> List[List[float]]:
    filtered_texts = [text.strip() for text in texts if text and text.strip()]

    if not filtered_texts:
        logger.warning("All input texts were empty after filtering")
        return []

    if len(filtered_texts) != len(texts):
        logger.warning(f"Filtered out {len(texts) - len(filtered_texts)} empty texts from {len(texts)} total texts")

    return _get_openai_embeddings(filtered_texts)


def _get_openai_embeddings(texts: List[str]) -> List[List[float]]:
    client = _get_openai_client()

    MAX_BATCH_SIZE = 2048

    embeddings: List[List[float]] = []
    for i in range(0, len(texts), MAX_BATCH_SIZE):
        batch = texts[i:i + MAX_BATCH_SIZE]
        try:
            response = client.embeddings.create(
                input=batch,
                model=OPENAI_EMBEDDING_MODEL
            )

            batch_embeddings = [data.embedding for data in response.data]
            embeddings.extend(batch_embeddings)

        except Exception as e:
            logger.exception(f"Error getting OpenAI embeddings: {e}")
            raise

    return embeddings


def get_embedding_dimension() -> int:
    if OPENAI_EMBEDDING_MODEL == "text-embedding-3-small":
        return 1536
    if OPENAI_EMBEDDING_MODEL == "text-embedding-3-large":
        return 3072
    if OPENAI_EMBEDDING_MODEL == "text-embedding-ada-002":
        return 1536
    raise ValueError(f"Unknown OpenAI model {OPENAI_EMBEDDING_MODEL}")


def get_model() -> OpenAI:
    return _get_openai_client()


def get_embedder_info() -> dict:
    return {
        "embedder_type": "openai",
        "model_name": OPENAI_EMBEDDING_MODEL,
        "dimension": get_embedding_dimension(),
    }