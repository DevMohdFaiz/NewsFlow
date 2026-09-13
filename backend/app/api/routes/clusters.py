import logging
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import PlainTextResponse
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
    days: int | None     = Query(default=None, description="Rolling window in days (defaults to settings.rolling_window_days)"),
    limit: int           = Query(default=16, ge=1, le=100),
    offset: int          = Query(default=0, ge=0),
):
    """
    Return paginated story clusters.
    Tries Redis top-stories cache first (first page, category-specific),
    falls back to Postgres with a joined query for title + source.
    """
    # Use config value as default so changing rolling_window_days in .env is respected
    effective_days = days if days is not None else settings.rolling_window_days

    if category and category not in settings.briefing_categories and category != "All":
        raise HTTPException(status_code=422, detail=f"Unknown category '{category}'")

    # Redis cache only for page 1 of a specific category
    if category and offset == 0:
        cached = store.redis.get_top_stories(category)
        if cached:
            logger.debug(f"[API] Clusters cache hit for {category}")
            total = await store.postgres.count_clusters(category=category, days=effective_days)
            return {
                "clusters": cached[:limit],
                "has_more": len(cached) > limit,
                "total":    total,
                "category": category,
                "days":     effective_days,
                "cached":   True,
            }

    # Postgres with JOIN
    clusters, has_more = await store.postgres.get_clusters_detailed(
        category=category,
        days=effective_days,
        limit=limit,
        offset=offset,
    )
    total = await store.postgres.count_clusters(category=category, days=effective_days)

    return {
        "clusters": clusters,
        "has_more": has_more,
        "total":    total,
        "category": category,
        "days":     effective_days,
        "cached":   False,
    }


@router.get("/search")
async def semantic_search(
    q: str               = Query(default="", description="Natural language search query"),
    category: str | None = Query(default=None, description="Optionally scope to a category"),
    top_k: int           = Query(default=12, ge=1, le=50, description="Number of results"),
):
    """
    Semantic search over ingested story clusters using Voyage AI embeddings + Qdrant.
    Returns results in the same Cluster shape as GET /api/clusters so the frontend needs no extra types.
    """
    q = q.strip()
    if not q:
        return {"clusters": [], "query": ""}

    if category and category not in settings.briefing_categories and category != "All":
        raise HTTPException(status_code=422, detail=f"Unknown category '{category}'")

    import asyncio
    from backend.app.processing.embedder import Embedder
    from backend.app.storage.store import store

    try:
        loop = asyncio.get_event_loop()
        embedder = Embedder()
        query_vector = await loop.run_in_executor(
            None, lambda: embedder.embed_query(q)
        )

        effective_category = category if (category and category != "All") else None
        raw_hits = await loop.run_in_executor(
            None,
            lambda: store.qdrant.search(
                query_vector=query_vector,
                category=effective_category,
                days=settings.rolling_window_days,
                top_k=top_k,
            ),
        )
    except Exception as exc:
        logger.error(f"[Search] Semantic search failed: {exc}", exc_info=True)
        raise HTTPException(status_code=503, detail="Semantic search temporarily unavailable")

    # Map Qdrant payload: Cluster shape expected by the frontend
    clusters = [
        {
            "cluster_id":         str(hit["id"]),
            "rep_title":          hit["payload"].get("title", ""),
            "summary":            hit["payload"].get("summary", ""),
            "source_count":       hit["payload"].get("source_count", 1),
            "sentiment_score":    hit["payload"].get("sentiment_score", 0.0),
            "sentiment_label":    hit["payload"].get("sentiment_label", "neutral"),
            "category":           hit["payload"].get("category", ""),
            "representative_url": hit["payload"].get("url", ""),
            "rep_source":         hit["payload"].get("source", ""),
            "entity_union":       hit["payload"].get("entity_union", []),
            "published_at":       hit["payload"].get("published_iso", ""),
            "_score":             round(hit["score"], 4),
        }
        for hit in raw_hits
    ]

    logger.info(f"[Search] '{q}' → {len(clusters)} results")
    return {"clusters": clusters, "query": q}


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
async def chat_about_cluster(cluster_id: str, req: ChatRequest, raw: bool | None = Query(default=None, description="If true, return raw markdown/plaintext instead of JSON")):
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
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_content},
            ],
            max_tokens=600,
            temperature=0.3,
        )
        reply = response.choices[0].message.content.strip()
        # If client asks for raw response, return as markdown/plaintext
        if raw:
            return PlainTextResponse(content=reply, media_type="text/markdown")
        return {"reply": reply}
    except Exception as e:
        logger.error(f"[Chat] Error for cluster {cluster_id}: {e}")
        raise HTTPException(status_code=500, detail="Chat request failed")
