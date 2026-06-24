import logging
import re
from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential
from config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

client         = Groq(api_key=settings.groq_api_key)
BRIEFING_MODEL = "llama-3.3-70b-versatile"


def _extractive_summary(texts: list[str], sentence_count: int = 3) -> str:
    """
    TextRank-based extractive summary.
    Picks the most representative sentences from the combined text.
    100% local — no API, no rate limits.
    """
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.nlp.tokenizers import Tokenizer
    from sumy.summarizers.text_rank import TextRankSummarizer

    combined = " ".join(t for t in texts if t and t.strip())
    if not combined.strip():
        return ""

    try:
        parser     = PlaintextParser.from_string(combined, Tokenizer("english"))
        summarizer = TextRankSummarizer()
        sentences  = summarizer(parser.document, sentence_count)
        return " ".join(str(s) for s in sentences).strip()
    except Exception:
        # Fallback: first N sentences of raw text
        raw_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', combined) if len(s.strip()) > 20]
        return " ".join(raw_sentences[:sentence_count])


class Summarizer:

    # Cluster Summaries — fully local, zero API calls

    def summarize_batch(self, clusters: list[dict]) -> list[dict]:
        """
        Summarize every cluster using extractive TextRank.
        Zero LLM calls — runs entirely in-process, no rate limits.
        """
        for cluster in clusters:
            cluster["summary"] = self._summarize_cluster(cluster)

        logger.info(f"[Summarizer] Extracted summaries for {len(clusters)} clusters (no API)")
        return clusters

    def _summarize_cluster(self, cluster: dict) -> str:
        """Build extractive summary from representative article."""
        rep  = cluster["representative"]
        body = (rep.get("body") or "").strip()
        desc = (rep.get("description") or "").strip()

        # If description is already substantial, use it directly (fast path)
        if len(desc) >= 120:
            return desc[:600]

        # If body is long enough, run TextRank extractive summarization
        if len(body) >= 200:
            texts = [body]
            # For multi-article clusters, add other titles for cross-source context
            for a in cluster.get("articles", []):
                if a is not rep:
                    t = (a.get("title") or "").strip()
                    if t:
                        texts.append(t)
            summary = _extractive_summary(texts, sentence_count=3)
            if summary:
                return summary

        # Final fallback: first 3 sentences of body, or desc, or title
        if body:
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', body) if len(s.strip()) > 20]
            if sentences:
                return " ".join(sentences[:3])
        return desc[:500] or rep.get("title", "")

    # Category Briefings — LLM, always exactly 8 calls

    def generate_all_briefings(self, clusters: list[dict]) -> dict[str, str]:
        """
        Generate one narrative briefing per category.
        Always exactly len(briefing_categories) LLM calls — independent of article count.
        """
        grouped: dict[str, list[dict]] = {}
        for cluster in clusters:
            cat = cluster.get("category", "Politics")
            grouped.setdefault(cat, []).append(cluster)

        briefings = {}
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_map = {}
            for category in settings.briefing_categories:
                cat_clusters = grouped.get(category, [])
                future = executor.submit(self._generate_briefing, category, cat_clusters)
                future_map[future] = category
                
            for future in as_completed(future_map):
                category = future_map[future]
                briefings[category] = future.result()

        return briefings

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def _generate_briefing(self, category: str, clusters: list[dict]) -> str:
        if not clusters:
            return f"No major {category} stories in the current news window."

        # Top 5 most-covered stories first
        top = sorted(clusters, key=lambda c: c.get("source_count", 1), reverse=True)[:5]

        stories_text = ""
        for i, c in enumerate(top, 1):
            rep     = c["representative"]
            summary = c.get("summary") or rep.get("description", "")
            sources = list({a.get("source", "") for a in c["articles"]})
            stories_text += (
                f"\nStory {i}: {rep.get('title', '')}\n"
                f"Sources: {', '.join(sources[:3])}\n"
                f"Summary: {summary}\n"
            )

        prompt = f"""You are an experienced news editor writing a daily briefing.

Write a concise bulleted summary of the key events for the {category} category,
synthesizing the top stories below.

Guidelines:
- Use markdown bullet points (-)
- Keep each bullet point to a single concise sentence
- Group related events together
- Do not use long-form prose or paragraphs
- Maximum 5 bullet points

Top {category} Stories:
{stories_text}"""

        try:
            response = client.chat.completions.create(
                model=BRIEFING_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.4,
            )
            briefing = response.choices[0].message.content.strip()
            logger.info(f"[Summarizer] Briefing generated for {category}")
            return briefing
        except Exception as e:
            logger.error(f"[Summarizer] Briefing failed for {category}: {e}")
            return f"Briefing temporarily unavailable for {category}."

    # Legacy alias kept for backward compat with ProcessingPipeline
    def generate_briefing(self, category: str, clusters: list[dict]) -> str:
        return self._generate_briefing(category, clusters)
