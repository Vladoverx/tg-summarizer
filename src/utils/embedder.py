import os
import logging
from typing import List, Optional, Union
from sentence_transformers import SentenceTransformer
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

EMBEDDER_TYPE = os.getenv("EMBEDDER_TYPE", "openai")
SENTENCE_TRANSFORMER_MODEL = "lang-uk/ukr-paraphrase-multilingual-mpnet-base"
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

_sentence_model: Optional[SentenceTransformer] = None
_openai_client: Optional[OpenAI] = None


def _get_sentence_model() -> SentenceTransformer:
    global _sentence_model
    if _sentence_model is None:
        logger.info(f"Loading sentence transformer model: {SENTENCE_TRANSFORMER_MODEL}")
        _sentence_model = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL)
        logger.info("Sentence transformer model loaded successfully")
    return _sentence_model


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
    
    if EMBEDDER_TYPE == "sentence_transformer":
        return _get_sentence_transformer_embeddings(filtered_texts)
    elif EMBEDDER_TYPE == "openai":
        return _get_openai_embeddings(filtered_texts)
    else:
        raise ValueError(f"Unknown embedder type: {EMBEDDER_TYPE}")


def _get_sentence_transformer_embeddings(texts: List[str]) -> List[List[float]]:
    model = _get_sentence_model()
    embeddings_tensor = model.encode(
        texts,
        convert_to_tensor=True,
        show_progress_bar=False,
        normalize_embeddings=True
    )
    return [vec.tolist() for vec in embeddings_tensor]


def _get_openai_embeddings(texts: List[str]) -> List[List[float]]:
    client = _get_openai_client()
    
    MAX_BATCH_SIZE = 2048
    
    embeddings = []
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
    if EMBEDDER_TYPE == "sentence_transformer":
        model = _get_sentence_model()
        dimension = model.get_sentence_embedding_dimension()
        if dimension is None:
            raise ValueError("Could not determine embedding dimension from sentence transformer model")
        return dimension
    elif EMBEDDER_TYPE == "openai":
        if OPENAI_EMBEDDING_MODEL == "text-embedding-3-small":
            return 1536
        elif OPENAI_EMBEDDING_MODEL == "text-embedding-3-large":
            return 3072
        elif OPENAI_EMBEDDING_MODEL == "text-embedding-ada-002":
            return 1536
        else:
            raise ValueError(f"Unknown OpenAI model {OPENAI_EMBEDDING_MODEL}")
    else:
        raise ValueError(f"Unknown embedder type: {EMBEDDER_TYPE}")


def get_model() -> Union[SentenceTransformer, OpenAI]:
    if EMBEDDER_TYPE == "sentence_transformer":
        return _get_sentence_model()
    elif EMBEDDER_TYPE == "openai":
        return _get_openai_client()
    else:
        raise ValueError(f"Unknown embedder type: {EMBEDDER_TYPE}")


def get_embedder_info() -> dict:
    info = {
        "embedder_type": EMBEDDER_TYPE,
        "dimension": get_embedding_dimension()
    }
    
    if EMBEDDER_TYPE == "sentence_transformer":
        info["model_name"] = SENTENCE_TRANSFORMER_MODEL
    elif EMBEDDER_TYPE == "openai":
        info["model_name"] = OPENAI_EMBEDDING_MODEL
    
    return info 