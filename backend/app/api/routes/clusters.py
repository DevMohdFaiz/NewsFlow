import logging
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from backend.app.storage.store import store
from config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clusters", tags=["clusters"])

VALID_CATEGORIES = set(settings.briefing_categories)


@router.get("")
async def get_clusters(
    category: str | None = Query(default=None, description="Filter by category"),
    days: int            = Query(default=3, ge=1, le=30, description="Rolling window in days"),
    limit: int           = Query(default=16, ge=1, le=100),
    offset: int          = Query(default=0, ge=0),
):
    """
    Return paginated story clusters.
    Tries Redis top-stories cache first (first page, category-specific),
    falls back to Postgres with a joined query for title + source.
    """
    if category and category not in VALID_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Unknown category '{category}'")

    # Redis cache only for page 1 of a specific category
    if category and offset == 0:
        cached = store.redis.get_top_stories(category)
        if cached:
            logger.debug(f"[API] Clusters cache hit for {category}")
            return {
                "clusters":  cached[:limit],
                "has_more":  len(cached) > limit,
                "category":  category,
                "days":      days,
                "cached":    True,
            }

    # Postgres with JOIN
    clusters, has_more = await store.postgres.get_clusters_detailed(
        category=category,
        days=days,
        limit=limit,
        offset=offset,
    )

    return {
        "clusters": clusters,
        "has_more": has_more,
        "category": category,
        "days":     days,
        "cached":   False,
    }


@router.get("/{cluster_id}")
async def get_cluster_detail(cluster_id: str):
    """Return a single cluster with all its source articles."""
    detail = await store.postgres.get_cluster_detail(cluster_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return detail


class ChatRequest(BaseModel):
    message: str
    cluster_context: str = ""   # pre-seeded context from the story


@router.post("/{cluster_id}/chat")
async def chat_about_cluster(cluster_id: str, req: ChatRequest):
    """
    Chat endpoint scoped to a specific cluster.
    Prefixes the user message with the cluster's context so the LLM
    answers specifically about this story.
    """
    from groq import Groq
    from config import get_settings
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    system_prompt = (
        "You are a knowledgeable news analyst. "
        "The user is reading a specific news story and wants to ask questions about it. "
        "Answer questions accurately based on the provided story context. "
        "Be concise and journalistic in tone. If the answer is not in the context, say so clearly."
    )

    context_block = f"STORY CONTEXT:\n{req.cluster_context}\n\n" if req.cluster_context else ""
    user_content = f"{context_block}USER QUESTION: {req.message}"

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            max_tokens=600,
            temperature=0.3,
        )
        reply = response.choices[0].message.content.strip()
        return {"reply": reply}
    except Exception as e:
        logger.error(f"[Chat] Error for cluster {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail="Chat request failed")
