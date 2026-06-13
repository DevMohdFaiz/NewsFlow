import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from newspaper import Article

logger = logging.getLogger(__name__)

MAX_WORKERS  = 100    # parallel extraction threads
MIN_BODY_LEN = 150   # discard articles with too little text

class ArticleExtractor:

    def extract_batch(self, articles: list[dict]) -> list[dict]:
        """Extract full body for all articles in parallel."""
        enriched = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_map = {
                executor.submit(self._extract_one, a): a
                for a in articles
            }
            for future in as_completed(future_map):
                try:
                    result = future.result()
                    if result:
                        enriched.append(result)
                except Exception as e:
                    original = future_map[future]
                    logger.debug(
                        f"[Extractor] Unhandled exception for "
                        f"{original.get('url', '?')}: {e}"
                    )

        logger.info(
            f"[Extractor] {len(enriched)}/{len(articles)} articles "
            f"passed extraction"
        )
        return enriched

    def _extract_one(self, article: dict) -> dict | None:
        """Download + parse a single article. Returns None if extraction fails."""
        url = article.get("url", "")

        # Skip download if body is already present (e.g. from Newsdata.io content field)
        existing_body = article.get("body", "").strip()
        if len(existing_body) >= MIN_BODY_LEN:
            return article

        from newspaper import Config
        try:
            conf = Config()
            conf.request_timeout = 5
            a = Article(url, config=conf)
            a.download()
            a.parse()

            body = a.text.strip()
            if len(body) < MIN_BODY_LEN:
                return None

            # Enrich with anything newspaper3k found
            article["body"]        = body
            article["title"]       = article["title"] or a.title or ""
            article["description"] = article["description"] or a.meta_description or ""

            # Use newspaper3k's publish date if we don't have one
            if not article.get("published_at") and a.publish_date:
                article["published_at"] = a.publish_date.isoformat()

            return article

        except Exception as e:
            logger.debug(f"[Extractor] Failed {url}: {e}")
            return None