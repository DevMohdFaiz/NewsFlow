import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import (
    String, Float, Integer, Text,
    DateTime, JSON, Index, text
)
from config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

# Engine
# asyncpg doesn't accept `sslmode` as a URL query param (that's a psycopg2/libpq
# convention). Strip it from the URL and pass ssl via connect_args instead.
import ssl as _ssl
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

def _build_asyncpg_url(raw_url: str) -> tuple[str, dict]:
    """
    Convert a Neon/postgres URL to asyncpg-compatible form:
      - swap postgresql:// → postgresql+asyncpg://
      - remove sslmode / ssl query params (asyncpg rejects them)
      - return connect_args with ssl context when ssl is required
    """
    # Swap dialect
    url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)

    # Detect whether SSL was requested
    ssl_mode = params.pop("sslmode", params.pop("ssl", [None]))[0]
    needs_ssl = ssl_mode in ("require", "verify-ca", "verify-full", "true", "1", "req")

    # Rebuild URL without any ssl* params
    clean_query = urlencode({k: v[0] for k, v in params.items()})
    clean_url   = urlunparse(parsed._replace(query=clean_query))

    connect_args = {}
    if needs_ssl:
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode   = _ssl.CERT_NONE   # Neon uses self-signed on free tier
        connect_args["ssl"] = ctx

    return clean_url, connect_args

_db_url, _connect_args = _build_asyncpg_url(settings.neon_database_url)

engine = create_async_engine(
    _db_url,
    connect_args=_connect_args,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,      # test connections before checking them out
    pool_recycle=1800,       # recycle connections older than 30 mins
    echo=False,
)


AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


#  Base 
class Base(DeclarativeBase):
    pass


#  Tables 
class ArticleModel(Base):
    __tablename__ = "articles"

    id:           Mapped[str]   = mapped_column(String, primary_key=True)   # uuid
    cluster_id:   Mapped[str]   = mapped_column(String, index=True)
    title:        Mapped[str]   = mapped_column(Text)
    url:          Mapped[str]   = mapped_column(String, unique=True)
    source:       Mapped[str]   = mapped_column(String)
    origin:       Mapped[str]   = mapped_column(String)          # newsapi | serpapi | rss
    body:         Mapped[str]   = mapped_column(Text)
    description:  Mapped[str]   = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at:   Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_articles_published_at_cluster", "published_at", "cluster_id"),
    )


class ClusterModel(Base):
    __tablename__ = "clusters"

    id:              Mapped[str]   = mapped_column(String, primary_key=True)  # cluster_id
    representative_url: Mapped[str] = mapped_column(String)
    category:        Mapped[str]   = mapped_column(String, index=True)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[str]   = mapped_column(String, nullable=True)
    summary:         Mapped[str]   = mapped_column(Text, nullable=True)
    entity_union:    Mapped[list]  = mapped_column(JSON, default=list)
    source_count:    Mapped[int]   = mapped_column(Integer, default=1)
    published_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at:      Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_clusters_category_published", "category", "published_at"),
    )


class BriefingModel(Base):
    __tablename__ = "briefings"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True, autoincrement=True)
    category:     Mapped[str]      = mapped_column(String, index=True)
    content:      Mapped[str]      = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True
    )


#  Init 
async def init_db():
    """Create all tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("[DB] Tables initialized")


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session