import logging

from backend.app.processing.ner import NERProcessor
from backend.app.processing.clusterer import SemanticClusterer
from backend.app.processing.classifier import CategoryClassifier
from backend.app.processing.sentiment import SentimentAnalyzer
from backend.app.processing.summarizer import Summarizer
from backend.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)


class ProcessingPipeline:
    def __init__(self):
        self.ner        = NERProcessor()
        self.clusterer  = SemanticClusterer()
        self.classifier = CategoryClassifier()
        self.sentiment  = SentimentAnalyzer()
        self.summarizer = Summarizer()

    def run(self, articles: list[dict]) -> list[dict]:
        """
        Takes clean articles from IngestionPipeline.
        Returns enriched story clusters ready for storage.
        """
        if not articles:
            logger.warning("[Processing] No articles to process")
            return []

        logger.info(f"[Processing] Starting with {len(articles)} articles")

        # Step 1 — NER entity extraction
        articles = self.ner.process_batch(articles)

        # Step 2 — NER-based candidate grouping
        candidate_clusters, singletons = self.ner.build_candidate_clusters(articles)

        # Step 3 — Semantic clustering (VoyageAI)
        clusters = self.clusterer.cluster(candidate_clusters, singletons)

        # Steps 4 & 5 — Category classification (keyword-based) + Sentiment (VADER)
        clusters = self.classifier.classify_batch(clusters)
        clusters = self.sentiment.analyze_batch(clusters)

        # Step 6 — Cluster summarization
        clusters = self.summarizer.summarize_batch(clusters)

        logger.info(f"[Processing] Complete => {len(clusters)} enriched clusters")
        return clusters

    def generate_all_briefings(self, clusters: list[dict]) -> dict[str, str]:
        """
        Group clusters by category and generate one briefing per category.
        Returns dict: { "Tech": "...", "Politics": "...", ... }
        """
        grouped: dict[str, list[dict]] = {}
        for cluster in clusters:
            cat = cluster.get("category", "Politics")
            grouped.setdefault(cat, []).append(cluster)

        briefings = {}
        for category in settings.briefing_categories:
            cat_clusters = grouped.get(category, [])
            briefings[category] = self.summarizer.generate_briefing(
                category, cat_clusters
            )

        return briefings