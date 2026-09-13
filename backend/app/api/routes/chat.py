import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Keep only the last N turns in the history sent to the LLM to cap context size
MAX_HISTORY_TURNS = 6

SYSTEM_PROMPT = """\
You are NewsFlow AI, an intelligent news assistant with access to today's top news stories.
Your job is to answer questions about current events based ONLY on the news context provided below.
Be concise, factual, and journalistic in tone.
If the provided context does not contain enough information to answer the question, say so clearly — \
do not hallucinate or invent facts.
When relevant, mention the specific stories or sources your answer is based on.\
"""


class ChatTurn(BaseModel):
    role: str    # "user" | "assistant"
    content: str


class GlobalChatRequest(BaseModel):
    message: str
    history: list[ChatTurn] = []


@router.post("")
async def global_chat(req: GlobalChatRequest):
    """
    RAG-powered global news chat.

    Flow:
      1. Embed the user message with Voyage AI
      2. Retrieve the top-5 semantically relevant clusters from Qdrant
      3. Build a grounded context block from those clusters
      4. Call the LLM (Groq) with the context + conversation history
      5. Return the reply + sources list
    """
    message = req.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be empty")

    from backend.app.processing.embedder import Embedder
    from backend.app.storage.store import store

    # ── 1. Embed the query ─────────────────────────────────────────────────
    try:
        embedder = Embedder()
        query_vector = await asyncio.get_event_loop().run_in_executor(
            None, lambda: embedder.embed_query(message)
        )
    except Exception as e:
        logger.error(f"[GlobalChat] Embedding failed: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Embedding service unavailable")

    # ── 2. Retrieve relevant clusters from Qdrant ──────────────────────────
    try:
        raw_hits = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: store.qdrant.search(
                query_vector=query_vector,
                category=None,           # global — search across all categories
                days=settings.rolling_window_days,
                top_k=5,
            ),
        )
    except Exception as e:
        logger.warning(f"[GlobalChat] Qdrant search failed, proceeding without context: {e}")
        raw_hits = []

    # ── 3. Build grounded context block ───────────────────────────────────
    sources = []
    context_lines = []

    if raw_hits:
        context_lines.append("CURRENT NEWS CONTEXT (use this to answer):\n")
        for i, hit in enumerate(raw_hits, 1):
            p = hit["payload"]
            title    = p.get("title", "Untitled")
            summary  = p.get("summary", "")
            category = p.get("category", "")
            source   = p.get("source", "")
            url      = p.get("url", "")

            context_lines.append(
                f"[Story {i}] {title}\n"
                f"Category: {category} | Source: {source}\n"
                f"Summary: {summary}\n"
            )
            sources.append({
                "cluster_id": str(hit["id"]),
                "title":      title,
                "category":   category,
                "source":     source,
                "url":        url,
                "score":      round(hit["score"], 4),
            })
        context_block = "\n".join(context_lines)
    else:
        context_block = (
            "NOTE: No news stories have been ingested yet. "
            "Inform the user politely that the news pipeline has not run yet "
            "and they should check back shortly."
        )

    # ── 4. Call Groq LLM ──────────────────────────────────────────────────
    try:
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)

        # Build message list: system + trimmed history + context-injected user turn
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Include recent history (capped) — exclude the very last user turn,
        # which we'll inject with context attached
        recent = req.history[-(MAX_HISTORY_TURNS * 2):]
        for turn in recent:
            messages.append({"role": turn.role, "content": turn.content})

        # Final user message = context block + actual question
        messages.append({
            "role": "user",
            "content": f"{context_block}\n\nUSER QUESTION: {message}",
        })

        def _call_llm():
            return client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=messages,
                max_tokens=700,
                temperature=0.3,
            )

        response = await asyncio.get_event_loop().run_in_executor(None, _call_llm)
        reply = response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"[GlobalChat] LLM call failed: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Chat service temporarily unavailable")

    logger.info(f"[GlobalChat] Answered '{message[:60]}…' using {len(sources)} sources")
    return {"reply": reply, "sources": sources}
