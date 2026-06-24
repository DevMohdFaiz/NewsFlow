import logging
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from groq import Groq
from config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

# Load VADER once at module level as it's fast and lightweight
_vader = SentimentIntensityAnalyzer()

client = Groq(api_key=settings.groq_api_key)
BRIEFING_MODEL = "llama-3.3-70b-versatile"


def _score_to_label(score: float) -> str:
    if score >=  0.5:
        return "very positive"
    elif score >=  0.2:
        return "positive"
    elif score >=  0.05:
        return "slightly positive"
    elif score > -0.05:
        return "neutral"
    elif score > -0.2: 
        return "slightly negative"
    elif score > -0.5:
        return "negative"
    else: 
        return "very negative"


class SentimentAnalyzer:

    def analyze_batch(self, clusters: list[dict]) -> list[dict]:
        """Score sentiment for all clusters instantly using VADER. Zero API calls."""
        for cluster in clusters:
            score, label = self._analyze_one(cluster)
            cluster["sentiment_score"] = score
            cluster["sentiment_label"] = label
        logger.info(f"[Sentiment] Scored {len(clusters)} clusters (VADER, no API)")
        return clusters

    def _analyze_one(self, cluster: dict) -> tuple[float, str]:
        rep   = cluster.get("representative", {})
        title = rep.get("title", "")
        desc  = rep.get("description", "") or rep.get("body", "")[:300]
        text  = f"{title}. {desc}"

        scores = _vader.polarity_scores(text)
        # compound score is already clamped to [-1.0, 1.0]
        compound = scores["compound"]
        return compound, _score_to_label(compound)