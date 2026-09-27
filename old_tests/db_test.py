import asyncio
from backend.config import get_settings
from backend.app.storage import database as dbmod
import asyncpg

async def main():
    settings = get_settings()
    url, connect_args = dbmod._build_asyncpg_url(settings.neon_database_url)
    # asyncpg expects a postgresql:// DSN (not postgresql+asyncpg://)
    async_dsn = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    print("DSN:", async_dsn)
    print("Connect args:", {k: type(v).__name__ for k,v in connect_args.items()})
    try:
        conn = await asyncpg.connect(dsn=async_dsn, timeout=30, **connect_args)
        print("Connected successfully")
        await conn.close()
    except Exception as e:
        print("Connection failed:", repr(e))

if __name__ == '__main__':
    asyncio.run(main())
