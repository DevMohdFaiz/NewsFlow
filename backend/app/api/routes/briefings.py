import logging
from fastapi import APIRouter, HTTPException

from backend.app.storage.store import store
from config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

router = APIRouter(prefix="/api/briefings", tags=["briefings"])

VALID_CATEGORIES = set(settings.briefing_categories)


@router.get("/{category}")
async def get_briefing(category: str):
    """
    Return the latest AI-generated briefing for a category.
    Tries Redis (2hr TTL) first, then Postgres.
    """
    if category == "All":
        return {
            "category": "All",
            "content": "Welcome to the NewsFlow live intelligence dashboard. Select a specific category from the sidebar to view its latest AI-generated briefing and analysis.",
            "cached": True
        }

    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown category '{category}'")

    # Redis fast path
    cached = store.redis.get_briefing(category)
    if cached:
        logger.debug(f"[API] Briefing cache hit for {category}")
        return {"category": category, "content": cached, "cached": True}

    # Postgres fallback
    content = await store.postgres.get_latest_briefing(category)
    if not content:
        return {
            "category": category,
            "content":  None,
            "cached":   False,
        }

    # Warm Redis for next request
    store.redis.set_briefing(category, content)

    return {"category": category, "content": content, "cached": False}
