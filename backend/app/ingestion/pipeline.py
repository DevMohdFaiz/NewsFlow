import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.app.ingestion.news_fetcher import NewsFetcher
from backend.app.ingestion.rss_fetcher  import RSSFetcher
from backend.app.ingestion.extractor    import ArticleExtractor
from backend.app.ingestion.normalizer   import Normalizer

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self):
        self.news_fetcher = NewsFetcher()
        self.rss_fetcher  = RSSFetcher()
        self.extractor    = ArticleExtractor()
        self.normalizer   = Normalizer()

    def run(self) -> list[dict]:
        logger.info("[Ingestion] Pipeline started")

        # 1. Fetch from all sources; run concurrently to cut latency
        # with ThreadPoolExecutor(max_workers=2) as executor:
        #     future_news = executor.submit(self.news_fetcher.fetch_all)
        #     future_rss  = executor.submit(self.rss_fetcher.fetch_all)

        #     newsapi_articles = future_news.result()
        #     rss_articles     = future_rss.result()

        # raw = newsapi_articles + rss_articles
        raw = self.rss_fetcher.fetch_all()
        logger.info(f"[Ingestion] Raw articles collected: {len(raw)}")

        # 2. Extract full body (already parallel inside ArticleExtractor)
        extracted = self.extractor.extract_batch(raw)

        # 3. Normalize, window, deduplicate
        clean = self.normalizer.normalize(extracted)

        logger.info(f"[Ingestion] Pipeline complete => {len(clean)} clean articles")
        return clean