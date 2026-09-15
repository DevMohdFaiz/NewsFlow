import logging
import spacy
from backend.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

# Load once at module level — disable everything except NER for speed
nlp = spacy.load("en_core_web_sm", disable=["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer"])

# Entity types we care about
ENTITY_TYPES = {"PERSON", "ORG", "GPE", "LOC", "NORP", "EVENT"}


class NERProcessor:

    def process_batch(self, articles: list[dict]) -> list[dict]:
        """Extract entities from each article. Adds 'entities' key using batched spaCy."""
        snippets = []
        for article in articles:
            title = article.get("title", "")
            body = article.get("body", "")
            sentences = body.split(".")[:3]
            snippet = title + ". " + ". ".join(sentences)
            snippets.append(snippet)

        docs = nlp.pipe(snippets, batch_size=50)

        for article, doc in zip(articles, docs):
            source_name = article.get("source", "").lower().strip()
            
            entities = []
            for ent in doc.ents:
                if ent.label_ in ENTITY_TYPES and len(ent.text.strip()) > 1:
                    text = ent.text.strip()
                    t_lower = text.lower()
                    
                    # Filter out publisher names from trending topics
                    if source_name and (t_lower in source_name or source_name in t_lower):
                        continue
                    
                    blacklist = ["news", "premium times", "bbc", "cnn", "nytimes", "al jazeera", "reuters", "bloomberg"]
                    if any(b in t_lower for b in blacklist):
                        continue
                        
                    entities.append(text)
                    
            article["entities"] = list(set(entities))

        return articles

    def build_candidate_clusters(
        self,
        articles: list[dict],
        window_hours: int = 6
    ) -> tuple[list[list[dict]], list[dict]]:
        """
        Group articles that share 2+ entities within the same time window
        into candidate clusters. Articles that share no entities with
        any group become singletons.

        Returns:
            candidate_clusters — list of article groups (need semantic check)
            singletons — articles that need individual embedding
        """
        from datetime import datetime, timezone, timedelta
        from dateutil import parser as dateparser

        def get_dt(a):
            try:
                return dateparser.parse(a["published_at"]).astimezone(timezone.utc)
            except Exception:
                return datetime.now(timezone.utc)

        clusters   = []   # list of lists
        singletons = []
        assigned   = set()

        # Precompute dt and entities
        parsed_data = []
        for a in articles:
            parsed_data.append({
                "ents": set(a.get("entities", [])),
                "dt": get_dt(a)
            })

        for i, article in enumerate(articles):
            if i in assigned:
                continue

            group   = [article]
            ents_i  = parsed_data[i]["ents"]
            dt_i    = parsed_data[i]["dt"]

            for j, other in enumerate(articles):
                if j <= i or j in assigned:
                    continue

                ents_j = parsed_data[j]["ents"]
                dt_j   = parsed_data[j]["dt"]
                
                time_diff = abs((dt_i - dt_j).total_seconds()) / 3600
                overlap   = len(ents_i & ents_j)

                if overlap >= 2 and time_diff <= window_hours:
                    group.append(other)
                    assigned.add(j)

            assigned.add(i)

            if len(group) > 1:
                clusters.append(group)
            else:
                singletons.append(article)

        logger.info(
            f"[NER] {len(clusters)} candidate clusters, "
            f"{len(singletons)} singletons"
        )
        return clusters, singletons 