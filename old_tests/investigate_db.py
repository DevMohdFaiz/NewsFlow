import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from backend.app.storage.database import AsyncSessionLocal, ClusterModel

async def investigate():
    print("\n" + "="*40)
    print("--- NewsFlow DB Investigation ---")
    print("="*40)

    async with AsyncSessionLocal() as session:
        # 1. Total clusters in DB
        result = await session.execute(select(func.count(ClusterModel.id)))
        total_clusters = result.scalar()
        print(f"\n1. Total articles (clusters) saved in Neon Database: {total_clusters}")

        if total_clusters == 0:
            print("\nCONCLUSION: Your database is completely empty. That's why the app shows the loading screen on startup!")
            return

        # 2. Latest 5 clusters regardless of date
        print("\n2. Latest 5 articles saved (ALL TIME):")
        result = await session.execute(
            select(ClusterModel.published_at, ClusterModel.category, ClusterModel.id)
            .order_by(ClusterModel.published_at.desc())
            .limit(5)
        )
        for row in result:
            print(f" - Published at: {row.published_at} | Category: {row.category}")

        # 3. How many clusters fall within the 3-day rolling window?
        from backend.config import get_settings
        settings = get_settings()

        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.rolling_window_days)
        print(f"\n3. Rolling Window Cutoff (Last {settings.rolling_window_days} days): {cutoff}")

        result = await session.execute(
            select(func.count(ClusterModel.id))
            .where(ClusterModel.published_at >= cutoff)
        )
        recent_clusters = result.scalar()
        print(f"-> Articles newer than cutoff (WHAT THE APP FETCHES ON STARTUP): {recent_clusters}")

        if recent_clusters == 0:
            print("\n" + "!"*40)
            print("CONCLUSION: The app returns 0 articles on startup because ALL saved articles are older than the rolling window!")
            print("The backend API filters out old news by default, forcing the frontend to show the 'Fetching the latest news...' screen.")
            print("To fix this, increase 'rolling_window_days' in config.py to something like 30.")
            print("!"*40 + "\n")
        else:
            print("\nCONCLUSION: The app SHOULD be displaying these recent articles instantly on startup!")

# if __name__ == "__main__":
#     import sys
#     if sys.platform == 'win32':
#         asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
#     asyncio.run(investigate())
