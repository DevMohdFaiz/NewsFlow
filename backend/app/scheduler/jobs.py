"""
Pipeline scheduler : runs the full ingest → process → store → briefing cycle.
"""
import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

# Shared executor for running blocking pipeline steps off the event loop
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipeline")

# Track whether a run is already in progress (prevent overlapping jobs)
_running = False


async def run_pipeline(*, trigger: str = "scheduler") -> dict:
    """
    Full pipeline:
      1. Ingest RSS → clean articles
      2. NER + Semantic clustering
      3. Classify + Sentiment + Summarize (all local, no LLM)
      4. Save clusters to Postgres + Qdrant
      5. Generate 8 category briefings (LLM)
      6. Save briefings + refresh Redis caches
    Returns a summary dict that can be returned from an API endpoint.
    """
    global _running
    if _running:
        logger.warning("[Scheduler] Pipeline already running : skipping this trigger")
        return {"status": "skipped", "reason": "already running"}

    _running = True
    t_start  = time.time()
    logger.info(f"[Scheduler] Pipeline triggered by: {trigger}")

    try:
        loop = asyncio.get_event_loop()

        #  1. Ingestion (blocking I/O : run in thread) 
        t_step = time.time()
        logger.info("[Scheduler] Step 1/6 : Ingestion")
        from backend.app.ingestion.pipeline import IngestionPipeline
        articles = await loop.run_in_executor(
            _executor, lambda: IngestionPipeline().run()
        )
        logger.info(f"[Scheduler] Step 1 complete in {time.time() - t_step:.1f}s (Ingested {len(articles)} articles)")

        if not articles:
            logger.warning("[Scheduler] No articles : aborting run")
            return {"status": "no_articles"}

        #  2–3. NER + Clustering (blocking CPU + network) 
        t_step = time.time()
        logger.info("[Scheduler] Steps 2-3 : NER + Semantic Clustering")
        from backend.app.processing.ner       import NERProcessor
        from backend.app.processing.clusterer import SemanticClusterer

        ner = NERProcessor()
        def _ner_cluster():
            arts = ner.process_batch(articles)
            candidates, singletons = ner.build_candidate_clusters(arts)
            return SemanticClusterer().cluster(candidates, singletons)

        clusters = await loop.run_in_executor(_executor, _ner_cluster)
        logger.info(f"[Scheduler] Steps 2-3 complete in {time.time() - t_step:.1f}s (Formed {len(clusters)} clusters)")

        #  4. Classify + Sentiment + Summarize (all local) 
        t_step = time.time()
        logger.info("[Scheduler] Step 4 : Classify + Sentiment + Summarize")
        from backend.app.processing.classifier import CategoryClassifier
        from backend.app.processing.sentiment  import SentimentAnalyzer
        from backend.app.processing.summarizer import Summarizer

        summarizer = Summarizer()

        def _enrich():
            c = CategoryClassifier().classify_batch(clusters)
            c = SentimentAnalyzer().analyze_batch(c)
            c = summarizer.summarize_batch(c)
            return c

        clusters = await loop.run_in_executor(_executor, _enrich)
        logger.info(f"[Scheduler] Step 4 complete in {time.time() - t_step:.1f}s")

        #  5. Persist to Postgres + Qdrant 
        t_step = time.time()
        logger.info("[Scheduler] Step 5 : Saving to Postgres + Qdrant")
        from backend.app.storage.store import store

        await store.postgres.save_clusters(clusters)

        def _qdrant_upsert():
            try:
                store.qdrant.upsert_clusters(clusters)
                store.qdrant.purge_old_points(days=settings.rolling_window_days)
            except Exception as qe:
                logger.warning(
                    f"[Scheduler] Qdrant upsert failed (non-fatal, vector search unavailable): {qe}"
                )

        await loop.run_in_executor(_executor, _qdrant_upsert)
        logger.info(f"[Scheduler] Step 5 complete in {time.time() - t_step:.1f}s")

        #  6. Generate briefings (8 LLM calls) 
        t_step = time.time()
        logger.info("[Scheduler] Step 6 : Generating category briefings")
        briefings = await loop.run_in_executor(
            _executor,
            lambda: summarizer.generate_all_briefings(clusters)
        )

        await store.postgres.save_briefings(briefings)
        store.redis.set_all_briefings(briefings)
        logger.info(f"[Scheduler] Step 6 complete in {time.time() - t_step:.1f}s")

        #  7. Refresh Redis dashboard caches 
        t_step = time.time()
        logger.info("[Scheduler] Step 7 : Refreshing Redis caches")
        try:
            sentiment = await store.postgres.get_sentiment_by_category()
            entities  = await store.postgres.get_trending_entities(limit=20)

            grouped: dict[str, list] = {}
            for c in clusters:
                cat = c.get("category", "Politics")
                grouped.setdefault(cat, []).append({
                    "cluster_id":      c["cluster_id"],
                    "category":        cat,
                    "summary":         c.get("summary", ""),
                    "sentiment_score": c.get("sentiment_score", 0.0),
                    "sentiment_label": c.get("sentiment_label", "neutral"),
                    "source_count":    c.get("source_count", 1),
                    "rep_title":       c["representative"].get("title", ""),
                    "rep_source":      c["representative"].get("source", ""),
                })

            store.redis.refresh_dashboard_cache(
                sentiment=sentiment,
                entities=entities,
                top_stories_by_category=grouped,
            )
            store.redis.set_all_briefings(briefings)
            logger.info(f"[Scheduler] Step 7 complete in {time.time() - t_step:.1f}s")
        except Exception as re:
            logger.warning(f"[Scheduler] Redis cache refresh failed (non-fatal): {re}")

        elapsed = time.time() - t_start
        result = {
            "status":       "ok",
            "trigger":      trigger,
            "articles":     len(articles),
            "clusters":     len(clusters),
            "briefings":    len(briefings),
            "elapsed_s":    round(elapsed, 1),
        }
        logger.info(f"[Scheduler] Pipeline complete in {elapsed:.1f}s : {result}")
        return result

    except Exception as e:
        elapsed = time.time() - t_start
        logger.error(f"[Scheduler] Pipeline failed after {elapsed:.1f}s: {e}", exc_info=True)
        return {"status": "error", "error": str(e), "elapsed_s": round(elapsed, 1)}

    finally:
        _running = False


def create_scheduler() -> AsyncIOScheduler:
    """
    Build and return a configured APScheduler instance.
    Call .start() on the returned scheduler to activate it.
    """
    scheduler = AsyncIOScheduler()

    # Full pipeline every N minutes (default: 30)
    scheduler.add_job(
        run_pipeline,
        trigger="interval",
        minutes=settings.ingestion_interval_minutes,
        id="pipeline_job",
        name="Full news pipeline",
        kwargs={"trigger": "scheduler"},
        max_instances=1,
        misfire_grace_time=60,
    )

    logger.info(
        f"[Scheduler] Scheduled pipeline every {settings.ingestion_interval_minutes} min"
    )
    return scheduler
