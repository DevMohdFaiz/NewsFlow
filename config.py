from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    groq_api_key: str =""
    voyageai_api_key: str =""
    news_api_key: str =""
    serp_api_key: str =""


    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()