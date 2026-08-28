from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    #  External API keys 
    groq_api_key: str
    voyageai_api_key: str
    news_api_key: str
    serp_api_key: str
    newsdata_api_key: str

    #  Qdrant 
    qdrant_api_key: str
    qdrant_cluster_endpoint: str   

    #  Neon Postgres 
    neon_database_url: str           # must start with postgresql+asyncpg://

    #  Upstash Redis 
    upstash_redis_rest_url:   str    # e.g. https://us1-xxxx.upstash.io
    upstash_redis_rest_token: str    # the token from the Upstash console

    #  Pipeline constants 
    qdrant_collection: str = "news_articles"
    rolling_window_days: int = 3
    briefing_categories: list[str] = [
        "All", "Nigeria", "Politics", "Economy", "Tech",
        "Health", "Science", "Conflict", "Climate", "Culture"
    ]
    ingestion_interval_minutes: int = 30
    briefing_interval_hours: int = 2
    similarity_threshold: float = 0.75   # cosine threshold for clustering
    top_k_chat_retrieval: int = 8

    model_config = SettingsConfigDict(env_file=".env")

@lru_cache
def get_settings() -> Settings:
    return Settings()