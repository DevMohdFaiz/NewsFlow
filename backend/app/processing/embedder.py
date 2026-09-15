import logging
import voyageai
from tenacity import retry, stop_after_attempt, wait_exponential
from backend.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

client = voyageai.Client(api_key=settings.voyageai_api_key)

EMBED_MODEL = "voyage-3"
BATCH_SIZE  = 128    # VoyageAI batch limit


class Embedder:

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts. Handles batching internally."""
        if not texts:
            return []

        all_embeddings = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            # @retry wraps only this single batch call so that a transient
            # failure doesn't re-send previously successful batches.
            embeddings = self._embed_batch(batch)
            all_embeddings.extend(embeddings)

        logger.info(f"[Embedder] Embedded {len(all_embeddings)} texts")
        return all_embeddings

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        """Embed a single batch with retry logic."""
        result = client.embed(batch, model=EMBED_MODEL, input_type="document")
        return result.embeddings

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def embed_query(self, query: str) -> list[float]:
        """Embed a single search query."""
        result = client.embed([query], model=EMBED_MODEL, input_type="query")
        return result.embeddings[0]

    def _article_text(self, article: dict) -> str:
        """Build the text we embed per article — title + description + body snippet."""
        title        = article.get("title", "")
        description  = article.get("description", "")
        body_snippet = article.get("body", "")[:500]   # first 500 chars
        return f"{title}. {description}. {body_snippet}".strip()