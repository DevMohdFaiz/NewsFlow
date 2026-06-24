from backend.app.storage.postgres_store import PostgresStore
from backend.app.storage.qdrant_store   import QdrantStore
from backend.app.storage.redis_store    import RedisStore
from backend.app.storage.database       import init_db


class Store:
    def __init__(self):
        self.postgres = PostgresStore()
        self.qdrant   = QdrantStore()
        self.redis    = RedisStore()

    async def init(self):
        """Initialize DB tables and Qdrant collection."""
        await init_db()
        self.qdrant.init_collection()


# Singleton
store = Store()