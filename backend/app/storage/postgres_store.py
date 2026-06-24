import logging
import uuid
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser

from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.storage.database import (
    ArticleModel, ClusterModel, BriefingModel, AsyncSessionLocal
)
from config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)


class PostgresStore:

    #  Clusters 
    async def save_clusters(self, clusters: list[dict]) -> None:
        """Upsert story clusters and their child articles."""
        async with AsyncSessionLocal() as session:
            for cluster in clusters:
                await self._upsert_cluster(session, cluster)
            await session.commit()
        logger.info(f"[Postgres] Saved {len(clusters)} clusters")

    async def _upsert_cluster(self, session: AsyncSession, cluster: dict) -> None:
        rep          = cluster["representative"]
        published_at = self._parse_dt(rep.get("published_at"))

        # Upsert cluster row
        stmt = insert(ClusterModel).values(
            id=cluster["cluster_id"],
            representative_url=rep.get("url", ""),
            category=cluster.get("category", "Politics"),
            sentiment_score=cluster.get("sentiment_score"),
            sentiment_label=cluster.get("sentiment_label"),
            summary=cluster.get("summary"),
            entity_union=cluster.get("entity_union", []),
            source_count=cluster.get("source_count", 1),
            published_at=published_at,
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "summary":         cluster.get("summary"),
                "sentiment_score": cluster.get("sentiment_score"),
                "sentiment_label": cluster.get("sentiment_label"),
                "source_count":    cluster.get("source_count", 1),
            }
        )
        await session.execute(stmt)

        # Upsert each article in the cluster
        for article in cluster.get("articles", []):
            await self._upsert_article(session, article, cluster["cluster_id"])

    async def _upsert_article(
        self, session: AsyncSession, article: dict, cluster_id: str
    ) -> None:
        stmt = insert(ArticleModel).values(
            id=str(uuid.uuid4()),
            cluster_id=cluster_id,
            title=article.get("title", ""),
            url=article.get("url", ""),
            source=article.get("source", ""),
            origin=article.get("origin", ""),
            body=article.get("body", ""),
            description=article.get("description", ""),
            published_at=self._parse_dt(article.get("published_at")),
        ).on_conflict_do_nothing(index_elements=["url"])
        await session.execute(stmt)

    #  Briefings 
    async def save_briefings(self, briefings: dict[str, str]) -> None:
        """Persist generated briefings."""
        async with AsyncSessionLocal() as session:
            for category, content in briefings.items():
                session.add(BriefingModel(
                    category=category,
                    content=content,
                    generated_at=datetime.now(timezone.utc)
                ))
            await session.commit()
        logger.info(f"[Postgres] Saved {len(briefings)} briefings")

    #  Queries 
    async def get_clusters(
        self,
        category: str | None = None,
        days: int = 3,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        async with AsyncSessionLocal() as session:
            query = select(ClusterModel).where(
                ClusterModel.published_at >= cutoff
            ).order_by(ClusterModel.published_at.desc())

            if category:
                query = query.where(ClusterModel.category == category)

            query = query.limit(limit).offset(offset)
            result = await session.execute(query)
            rows = result.scalars().all()
            return [self._cluster_to_dict(r) for r in rows]

    async def get_clusters_detailed(
        self,
        category: str | None = None,
        days: int = 3,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], bool]:
        """
        Like get_clusters but LEFT JOINs with ArticleModel to include the
        representative article's title and source name.

        Returns (clusters, has_more) where has_more indicates if there are
        additional pages beyond this result set.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        async with AsyncSessionLocal() as session:
            stmt = (
                select(
                    ClusterModel,
                    ArticleModel.title.label("rep_title"),
                    ArticleModel.source.label("rep_source"),
                )
                .join(
                    ArticleModel,
                    ArticleModel.url == ClusterModel.representative_url,
                    isouter=True,
                )
                .where(ClusterModel.published_at >= cutoff)
                .order_by(ClusterModel.published_at.desc())
            )

            if category:
                stmt = stmt.where(ClusterModel.category == category)

            # Fetch one extra row to determine has_more
            stmt = stmt.limit(limit + 1).offset(offset)
            result = await session.execute(stmt)
            rows = result.all()

        has_more = len(rows) > limit
        rows = rows[:limit]

        clusters = [
            {
                **self._cluster_to_dict(row[0]),
                "rep_title":  row[1] or "",
                "rep_source": row[2] or "Unknown",
            }
            for row in rows
        ]
        return clusters, has_more

    async def get_cluster_detail(self, cluster_id: str) -> dict | None:
        """
        Return a single cluster with all its child articles included.
        Used by the story detail panel.
        """
        async with AsyncSessionLocal() as session:
            # Fetch the cluster row
            cluster_row = await session.get(ClusterModel, cluster_id)
            if not cluster_row:
                return None

            # Fetch all articles in this cluster
            articles_result = await session.execute(
                select(ArticleModel)
                .where(ArticleModel.cluster_id == cluster_id)
                .order_by(ArticleModel.published_at.desc())
            )
            articles = articles_result.scalars().all()

        cluster_dict = self._cluster_to_dict(cluster_row)
        cluster_dict["articles"] = [
            {
                "title":        a.title,
                "url":          a.url,
                "source":       a.source,
                "published_at": a.published_at.isoformat(),
                "description":  a.description or "",
            }
            for a in articles
        ]
        return cluster_dict


    async def count_clusters(
        self,
        category: str | None = None,
        days: int = 3,
    ) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        async with AsyncSessionLocal() as session:
            stmt = select(func.count(ClusterModel.id)).where(
                ClusterModel.published_at >= cutoff
            )
            if category:
                stmt = stmt.where(ClusterModel.category == category)
            result = await session.execute(stmt)
            return result.scalar_one() or 0

    async def get_latest_briefing(self, category: str) -> str | None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(BriefingModel)
                .where(BriefingModel.category == category)
                .order_by(BriefingModel.generated_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return row.content if row else None

    async def get_sentiment_by_category(self) -> dict[str, float]:
        """Average sentiment score per category for dashboard."""
        async with AsyncSessionLocal() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=3)
            result = await session.execute(
                select(
                    ClusterModel.category,
                    func.avg(ClusterModel.sentiment_score).label("avg_sentiment"),
                    func.count(ClusterModel.id).label("count")
                )
                .where(ClusterModel.published_at >= cutoff)
                .group_by(ClusterModel.category)
            )
            return {
                row.category: round(float(row.avg_sentiment or 0), 3)
                for row in result.all()
            }

    async def get_trending_entities(self, limit: int = 20) -> list[dict]:
        """Most frequently appearing entities in the last 3 days."""
        from collections import Counter
        clusters = await self.get_clusters(days=3, limit=200)
        entity_counter: Counter = Counter()
        for c in clusters:
            for entity in c.get("entity_union", []):
                entity_counter[entity] += 1
        return [
            {"entity": e, "count": cnt}
            for e, cnt in entity_counter.most_common(limit)
        ]

    async def get_last_pipeline_at(self) -> str | None:
        """Return the ISO timestamp of the most recently created cluster."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ClusterModel.created_at)
                .order_by(ClusterModel.created_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return row.isoformat() if row else None

    async def get_cluster_counts(self, days: int = 3) -> dict[str, int]:
        """Return story count per category for the given rolling window."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(
                    ClusterModel.category,
                    func.count(ClusterModel.id).label("cnt"),
                )
                .where(ClusterModel.published_at >= cutoff)
                .group_by(ClusterModel.category)
            )
            return {row.category: row.cnt for row in result.all()}

    #  Cleanup 
    async def purge_old_clusters(self, days: int = 7) -> None:
        """Weekly trim remove clusters older than N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                delete(ClusterModel).where(ClusterModel.published_at < cutoff)
            )
            await session.commit()
            logger.info(f"[Postgres] Purged clusters older than {days} days")

    #  Helpers 
    def _parse_dt(self, value) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        try:
            return dateparser.parse(str(value)).astimezone(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    def _cluster_to_dict(self, row: ClusterModel) -> dict:
        return {
            "cluster_id":      row.id,
            "category":        row.category,
            "sentiment_score": row.sentiment_score,
            "sentiment_label": row.sentiment_label,
            "summary":         row.summary,
            "entity_union":    row.entity_union or [],
            "source_count":    row.source_count,
            "published_at":    row.published_at.isoformat(),
            "representative_url": row.representative_url,
        }