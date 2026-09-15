import logging
import json
from datetime import timedelta
from upstash_redis import Redis
from backend.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

redis = Redis(
    url=settings.upstash_redis_rest_url,
    token=settings.upstash_redis_rest_token,
)

# TTLs (in seconds)
TTL_BRIEFING   = 60 * 60 * 2       # 2 hours
TTL_DASHBOARD  = 60 * 30           # 30 minutes
TTL_SENTIMENT  = 60 * 30           # 30 minutes
TTL_ENTITIES   = 60 * 30           # 30 minutes

# Key prefixes
KEY_BRIEFING   = "briefing:{category}"
KEY_DASHBOARD  = "dashboard:summary"
KEY_SENTIMENT  = "dashboard:sentiment"
KEY_ENTITIES   = "dashboard:entities"
KEY_TOP_STORIES = "dashboard:top_stories:{category}"


class RedisStore:

    def _get_safe(self, key: str) -> str | None:
        try:
            return redis.get(key)
        except Exception as e:
            logger.warning(f"[Redis] GET failed for key {key}: {e}")
            return None

    def _set_safe(self, key: str, value: str, ex: int | None = None) -> bool:
        try:
            redis.set(key, value, ex=ex)
            return True
        except Exception as e:
            logger.warning(f"[Redis] SET failed for key {key}: {e}")
            return False

    #  Briefings 
    def set_briefing(self, category: str, content: str) -> None:
        key = KEY_BRIEFING.format(category=category)
        self._set_safe(key, content, ex=TTL_BRIEFING)
        logger.debug(f"[Redis] Cached briefing for {category}")

    def get_briefing(self, category: str) -> str | None:
        key = KEY_BRIEFING.format(category=category)
        return self._get_safe(key)

    def set_all_briefings(self, briefings: dict[str, str]) -> None:
        for category, content in briefings.items():
            self.set_briefing(category, content)
        logger.info(f"[Redis] Cached {len(briefings)} briefings")

    #  Dashboard aggregates 
    def set_sentiment(self, sentiment_by_category: dict[str, float]) -> None:
        self._set_safe(
            KEY_SENTIMENT,
            json.dumps(sentiment_by_category),
            ex=TTL_SENTIMENT,
        )

    def get_sentiment(self) -> dict[str, float] | None:
        raw = self._get_safe(KEY_SENTIMENT)
        return json.loads(raw) if raw else None

    def set_trending_entities(self, entities: list[dict]) -> None:
        self._set_safe(
            KEY_ENTITIES,
            json.dumps(entities),
            ex=TTL_ENTITIES,
        )

    def get_trending_entities(self) -> list[dict] | None:
        raw = self._get_safe(KEY_ENTITIES)
        return json.loads(raw) if raw else None

    def set_top_stories(self, category: str, stories: list[dict]) -> None:
        key = KEY_TOP_STORIES.format(category=category)
        self._set_safe(key, json.dumps(stories), ex=TTL_DASHBOARD)

    def get_top_stories(self, category: str) -> list[dict] | None:
        key = KEY_TOP_STORIES.format(category=category)
        raw = self._get_safe(key)
        return json.loads(raw) if raw else None

    def set_dashboard_summary(self, data: dict) -> None:
        self._set_safe(KEY_DASHBOARD, json.dumps(data), ex=TTL_DASHBOARD)

    def get_dashboard_summary(self) -> dict | None:
        raw = self._get_safe(KEY_DASHBOARD)
        return json.loads(raw) if raw else None

    #  Cache refresh 
    def refresh_dashboard_cache(
        self,
        sentiment: dict,
        entities: list[dict],
        top_stories_by_category: dict[str, list[dict]],
    ) -> None:
        """Called after every ingestion cycle."""
        self.set_sentiment(sentiment)
        self.set_trending_entities(entities)
        for category, stories in top_stories_by_category.items():
            self.set_top_stories(category, stories)
        logger.info("[Redis] Dashboard cache refreshed")