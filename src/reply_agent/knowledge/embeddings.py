from functools import lru_cache

import voyageai

from reply_agent.config import get_settings


@lru_cache
def get_voyage_client() -> voyageai.Client:
    # Free-tier accounts (no payment method on file) are capped at 3 requests/minute — the
    # client's built-in retry-with-backoff handles that transparently instead of erroring.
    return voyageai.Client(api_key=get_settings().voyage_api_key, max_retries=5)


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed knowledge-base chunks for storage (retrieve_knowledge embeds queries separately)."""
    if not texts:
        return []
    result = get_voyage_client().embed(
        texts, model=get_settings().voyage_embedding_model, input_type="document"
    )
    return result.embeddings


def embed_query(text: str) -> list[float]:
    result = get_voyage_client().embed(
        [text], model=get_settings().voyage_embedding_model, input_type="query"
    )
    return result.embeddings[0]
