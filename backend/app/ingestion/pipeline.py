import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.app.ingestion.rss_fetcher import RSSFetcher
from backend.app.ingestion.extractor import ArticleExtractor
from backend.app.ingestion.normalizer import Normalizer

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self):
        self.rss_fetcher  = RSSFetcher()
        self.extractor    = ArticleExtractor()
        self.normalizer   = Normalizer()

    def run(self) -> list[dict]:
        logger.info("[Ingestion] Pipeline started")

        raw = self.rss_fetcher.fetch_all()
        logger.info(f"[Ingestion] Raw articles collected: {len(raw)}")

        # 2. Extract full body (already parallel inside ArticleExtractor)
        extracted = self.extractor.extract_batch(raw)

        # 3. Normalize, window, deduplicate
        clean = self.normalizer.normalize(extracted)

        logger.info(f"[Ingestion] Pipeline complete => {len(clean)} clean articles")
        return clean