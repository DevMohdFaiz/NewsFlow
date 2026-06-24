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
        # Build a dynamic "top headlines" summary from the 5 most recent clusters
        top_clusters = await store.postgres.get_clusters_detailed(
            category=None, days=3, limit=5, offset=0
        )
        clusters_list = top_clusters[0]  # (clusters, has_more) tuple

        if not clusters_list:
            return {
                "category": "All",
                "content": None,
                "cached": False,
            }

        lines = []
        for c in clusters_list:
            title = c.get("rep_title") or ""
            summary = c.get("summary") or ""
            cat = c.get("category", "")
            source_count = c.get("source_count", 1)
            line = f"{title} [{cat}, {source_count} source{'s' if source_count != 1 else ''}]"
            if summary:
                line += f" — {summary[:120].rstrip()}{'…' if len(summary) > 120 else ''}"
            lines.append(f"• {line}")

        content = "\n".join(lines)
        return {
            "category": "All",
            "content": content,
            "cached": False,
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
