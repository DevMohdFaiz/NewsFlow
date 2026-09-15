import logging
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, Range, MatchValue,
    PayloadSchemaType
)

from backend.config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

COLLECTION   = settings.qdrant_collection
VECTOR_SIZE  = 1024    # voyage-3 output dimension


class QdrantStore:

    def __init__(self):
        self.client = QdrantClient(
            url=settings.qdrant_cluster_endpoint,
            api_key=settings.qdrant_api_key,
            timeout=60,          # Increased from 10 to 60s for larger upserts
        )

    #  Setup 
    def init_collection(self) -> None:
        """Create collection if it doesn't already exist."""
        existing = [c.name for c in self.client.get_collections().collections]
        if COLLECTION in existing:
            logger.info(f"[Qdrant] Collection '{COLLECTION}' already exists")
            return

        self.client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )

        # Create payload indexes for fast filtering
        for field, schema in [
            ("category",     PayloadSchemaType.KEYWORD),
            ("published_at", PayloadSchemaType.FLOAT),
        ]:
            self.client.create_payload_index(
                collection_name=COLLECTION,
                field_name=field,
                field_schema=schema,
            )

        logger.info(f"[Qdrant] Collection '{COLLECTION}' created with indexes")

    #  Write 
    def upsert_clusters(self, clusters: list[dict]) -> None:
        """Store cluster embeddings + rich payload in Qdrant."""
        points = []
        for cluster in clusters:
            embedding = cluster.get("embedding")
            if not embedding:
                continue

            rep          = cluster["representative"]
            published_ts = self._to_timestamp(rep.get("published_at"))
            sources      = list({a.get("source", "") for a in cluster["articles"]})

            points.append(PointStruct(
                id=cluster["cluster_id"],
                vector=embedding,
                payload={
                    "title":           rep.get("title", ""),
                    "url":             rep.get("url", ""),
                    "source":          rep.get("source", ""),
                    "all_sources":     sources,
                    "category":        cluster.get("category", "Politics"),
                    "sentiment_score": cluster.get("sentiment_score", 0.0),
                    "sentiment_label": cluster.get("sentiment_label", "neutral"),
                    "summary":         cluster.get("summary", ""),
                    "entity_union":    cluster.get("entity_union", []),
                    "source_count":    cluster.get("source_count", 1),
                    "published_at":    published_ts,  # stored as unix timestamp
                    "published_iso":   rep.get("published_at", ""),
                },
            ))

        if not points:
            logger.warning("[Qdrant] No valid points to upsert")
            return

        self.client.upsert(collection_name=COLLECTION, points=points)
        logger.info(f"[Qdrant] Upserted {len(points)} points")

    #  Search 
    def search(
        self,
        query_vector: list[float],
        category: str | None = None,
        days: int = 3,
        top_k: int = 8,
    ) -> list[dict]:
        """
        Semantic search with payload filtering.
        Filter by date window and optionally by category.
        """
        cutoff_ts = self._cutoff_timestamp(days)

        must_conditions = [
            FieldCondition(
                key="published_at",
                range=Range(gte=cutoff_ts),
            )
        ]

        if category:
            must_conditions.append(
                FieldCondition(
                    key="category",
                    match=MatchValue(value=category),
                )
            )

        results = self.client.search(
            collection_name=COLLECTION,
            query_vector=query_vector,
            query_filter=Filter(must=must_conditions),
            limit=top_k,
            with_payload=True,
        )

        return [
            {
                "score":   hit.score,
                "payload": hit.payload,
                "id":      hit.id,
            }
            for hit in results
        ]

    #  Cleanup 
    def purge_old_points(self, days: int = 3) -> None:
        """Remove vectors older than the rolling window."""
        cutoff_ts = self._cutoff_timestamp(days)
        self.client.delete(
            collection_name=COLLECTION,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="published_at",
                        range=Range(lt=cutoff_ts),
                    )
                ]
            ),
        )
        logger.info(f"[Qdrant] Purged points older than {days} days")

    #  Helpers 
    def _to_timestamp(self, value) -> float:
        """Convert ISO string or datetime to unix timestamp."""
        try:
            if isinstance(value, (int, float)):
                return float(value)
            dt = dateparser.parse(str(value)).astimezone(timezone.utc)
            return dt.timestamp()
        except Exception:
            return datetime.now(timezone.utc).timestamp()

    def _cutoff_timestamp(self, days: int) -> float:
        return (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()