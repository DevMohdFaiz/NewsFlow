from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    groq_api_key: str 
    voyageai_api_key: str 
    news_api_key: str 
    serp_api_key: str 
    newsdata_api_key: str

    # Pipeline constants
    qdrant_collection: str = "news_articles"
    rolling_window_days: int = 3
    briefing_categories: list[str] = [
        "Politics", "Economy", "Tech",
        "Health", "Science", "Conflict", "Climate", "Culture"
    ]
    ingestion_interval_minutes: int = 30
    briefing_interval_hours: int = 2
    similarity_threshold: float = 0.82   # cosine threshold for clustering
    top_k_chat_retrieval: int = 8

    model_config = SettingsConfigDict(env_file=".env")
    
    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()