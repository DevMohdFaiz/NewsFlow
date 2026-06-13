import logging
import uuid
import hashlib
import numpy as np
from .embedder import Embedder
from config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = settings.similarity_threshold


class SemanticClusterer:

    def __init__(self):
        self.embedder = Embedder()

    def cluster(
        self,
        candidate_clusters: list[list[dict]],
        singletons: list[dict]
    ) -> list[dict]:
        """
        Takes NER-formed candidate groups and singletons.
        - Candidate groups: embed one representative per group,
          then verify similarity ≥ threshold. If not similar enough,
          split into singletons.
        - Singletons: embed individually and cluster against existing groups
          using semantic similarity.

        Returns a flat list of story clusters, each with:
            cluster_id, articles, representative_article,
            embedding, entity_union
        """
        # 1. Collect all texts that need to be embedded to do one bulk API call
        texts_to_embed = set()
        
        representatives = [self._pick_representative(g) for g in candidate_clusters]
        for rep in representatives:
            texts_to_embed.add(self._embed_text(rep))
            
        for i, group in enumerate(candidate_clusters):
            rep = representatives[i]
            for member in group:
                if member != rep:
                    texts_to_embed.add(self._embed_text(member))
                    
        for s in singletons:
            texts_to_embed.add(self._embed_text(s))
            
        # Bulk embed
        unique_texts = list(texts_to_embed)
        embeddings = self.embedder.embed_texts(unique_texts) if unique_texts else []
        text_to_embed_map = dict(zip(unique_texts, embeddings))

        story_clusters = []

        # Process candidate clusters 
        for i, group in enumerate(candidate_clusters):
            rep        = representatives[i]
            rep_text   = self._embed_text(rep)
            rep_embed  = text_to_embed_map[rep_text]

            confirmed_group = [rep]

            for member in group:
                if member == rep:
                    continue
                member_text = self._embed_text(member)
                member_embed = text_to_embed_map[member_text]
                
                sim = self._cosine(rep_embed, member_embed)
                if sim >= SIMILARITY_THRESHOLD:
                    confirmed_group.append(member)
                else:
                    # If it doesn't meet the threshold, add to singletons for global clustering
                    singletons.append(member)

            story_clusters.append({
                "representative": rep,
                "embedding": rep_embed,
                "articles": confirmed_group
            })

        # Process singletons with greedy semantic clustering
        for article in singletons:
            article_text = self._embed_text(article)
            article_embed = text_to_embed_map[article_text]
            
            best_sim = 0.0
            best_cluster = None
            
            for sc in story_clusters:
                sim = self._cosine(article_embed, sc["embedding"])
                if sim > best_sim:
                    best_sim = sim
                    best_cluster = sc
                    
            if best_sim >= SIMILARITY_THRESHOLD:
                best_cluster["articles"].append(article)
            else:
                # Become a new cluster
                story_clusters.append({
                    "representative": article,
                    "embedding": article_embed,
                    "articles": [article]
                })

        # Finalize format
        final_clusters = []
        for sc in story_clusters:
            final_clusters.append(
                self._build_cluster(sc["articles"], sc["representative"], sc["embedding"])
            )

        logger.info(f"[Clusterer] Formed {len(final_clusters)} story clusters from semantic clustering")
        return final_clusters

    #  Helpers 

    def _build_cluster(
        self,
        articles: list[dict],
        representative: dict,
        embedding: list[float]
    ) -> dict:
        all_entities = []
        for a in articles:
            all_entities.extend(a.get("entities", []))

        return {
            "cluster_id":           hashlib.md5(representative.get("url", "").encode()).hexdigest(),
            "articles":             articles,
            "representative":       representative,
            "embedding":            embedding,
            "entity_union":         list(set(all_entities)),
            "source_count":         len(articles),
            # Fields filled by later processors — intentionally absent until set
        }

    def _pick_representative(self, group: list[dict]) -> dict:
        """Pick the article with the longest body as the representative."""
        return max(group, key=lambda a: len(a.get("body", "")))

    def _embed_text(self, article: dict) -> str:
        title        = article.get("title", "")
        description  = article.get("description", "")
        body_snippet = article.get("body", "")[:500]
        return f"{title}. {description}. {body_snippet}".strip()

    def _cosine(self, a: list[float], b: list[float]) -> float:
        va = np.array(a)
        vb = np.array(b)
        denom = np.linalg.norm(va) * np.linalg.norm(vb)
        if denom == 0:
            return 0.0
        return float(np.dot(va, vb) / denom)