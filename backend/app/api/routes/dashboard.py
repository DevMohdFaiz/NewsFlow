import logging
from datetime import datetime, timezone
from fastapi import APIRouter

from backend.app.storage.store import store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard():
    """
    Aggregate dashboard data: sentiment by category + trending entities.
    Serves from Redis cache where available; falls back to Postgres.
    """
    #  Sentiment 
    sentiment = store.redis.get_sentiment()
    if not sentiment:
        sentiment = await store.postgres.get_sentiment_by_category()
        if sentiment:
            store.redis.set_sentiment(sentiment)

    #  Trending entities 
    entities = store.redis.get_trending_entities()
    if not entities:
        entities = await store.postgres.get_trending_entities(limit=20)
        if entities:
            store.redis.set_trending_entities(entities)

    return {
        "sentiment_by_category": sentiment or {},
        "trending_entities":     entities or [],
        "server_time":           datetime.now(timezone.utc).isoformat(),
    }
