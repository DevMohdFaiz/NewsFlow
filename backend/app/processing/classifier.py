import logging
import re
from config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

CATEGORIES = settings.briefing_categories

# Keyword map — each category has a list of keywords/phrases.
# Order matters: checked top-to-bottom. Put more specific categories first.
KEYWORD_MAP: list[tuple[str, list[str]]] = [
    ("Conflict", [
        "war", "military", "attack", "bomb", "missile", "troops", "soldier",
        "ceasefire", "killed", "airstrike", "insurgent", "rebel", "invasion",
        "offensive", "artillery", "drone strike", "combat", "hostage",
        "wounded", "casualties", "coup", "siege", "frontline", "armed",
        "terrorist", "terrorism", "isis", "hamas", "hezbollah", "nato forces",
        "ukraine", "russia", "gaza", "conflict zone",
    ]),
    ("Climate", [
        "climate", "global warming", "carbon", "emissions", "fossil fuel",
        "renewable energy", "solar", "wind energy", "drought", "flood",
        "wildfire", "hurricane", "cyclone", "sea level", "glacier",
        "deforestation", "biodiversity", "cop", "net zero", "greenhouse",
        "pollution", "ozone", "arctic", "coral reef", "extreme weather",
    ]),
    ("Health", [
        "health", "hospital", "disease", "vaccine", "pandemic", "virus",
        "cancer", "mental health", "drug", "pharmaceutical", "medicine",
        "surgery", "outbreak", "epidemic", "public health", "nutrition",
        "obesity", "diabetes", "hiv", "aids", "who ", "fda", "nhs",
        "clinical trial", "therapy", "patient", "doctor", "nurse",
    ]),
    ("Science", [
        "nasa", "space", "asteroid", "galaxy", "telescope", "quantum",
        "physics", "biology", "genetics", "dna", "research", "study",
        "discovery", "scientists", "experiment", "laboratory", "rover",
        "satellite", "black hole", "exoplanet", "stem cell", "genome",
        "evolution", "fossil", "archaeology", "neuroscience", "crispr",
    ]),
    ("Tech", [
        "ai", "artificial intelligence", "machine learning", "chatgpt",
        "openai", "google", "microsoft", "apple", "meta", "amazon",
        "startup", "software", "hardware", "chip", "semiconductor",
        "cybersecurity", "hack", "data breach", "robotics", "autonomous",
        "cryptocurrency", "bitcoin", "blockchain", "app", "cloud",
        "elon musk", "tesla", "spacex", "nvidia", "algorithm", "model",
        "llm", "chatbot", "deepmind", "anthropic", "gemini", "gpt",
    ]),
    ("Economy", [
        "economy", "gdp", "inflation", "interest rate", "federal reserve",
        "central bank", "stock market", "recession", "trade", "tariff",
        "unemployment", "jobs", "wages", "imf", "world bank", "debt",
        "deficit", "budget", "fiscal", "monetary", "oil price", "crude",
        "dollar", "euro", "currency", "investment", "bond", "treasury",
        "market", "shares", "earnings", "profit", "revenue", "finance",
    ]),
    ("Culture", [
        "film", "movie", "music", "album", "concert", "artist", "award",
        "oscar", "grammy", "netflix", "disney", "book", "novel", "author",
        "sport", "football", "soccer", "basketball", "tennis", "olympics",
        "fashion", "celebrity", "actor", "actress", "director", "museum",
        "art", "culture", "theater", "theatre", "festival", "chef",
    ]),
    # Politics is the catch-all — always last
    ("Politics", [
        "president", "prime minister", "parliament", "congress", "senate",
        "election", "vote", "government", "minister", "policy", "law",
        "legislation", "democrat", "republican", "party", "diplomat",
        "sanction", "treaty", "un ", "united nations", "summit", "biden",
        "trump", "macron", "leader", "chancellor", "monarchy", "court",
        "supreme court", "protest", "rally", "opposition",
    ]),
]


class CategoryClassifier:

    def classify_batch(self, clusters: list[dict]) -> list[dict]:
        """Classify all clusters instantly via keyword matching. Zero API calls."""
        for cluster in clusters:
            cluster["category"] = self._classify_one(cluster)
        logger.info(f"[Classifier] Classified {len(clusters)} clusters (keyword-based, no API)")
        return clusters

    def _classify_one(self, cluster: dict) -> str:
        rep   = cluster.get("representative", {})
        title = rep.get("title", "").lower()
        desc  = rep.get("description", "").lower() or rep.get("body", "").lower()[:500]
        text  = f"{title} {desc}"

        scores: dict[str, int] = {cat: 0 for cat, _ in KEYWORD_MAP}

        for category, keywords in KEYWORD_MAP:
            for kw in keywords:
                if re.search(r'\b' + re.escape(kw) + r'\b', text):
                    scores[category] += 1

        # Pick the category with the highest keyword hit count
        best_cat = max(scores, key=lambda c: scores[c])
        if scores[best_cat] == 0:
            return "Politics"   # Catch-all fallback
        return best_cat