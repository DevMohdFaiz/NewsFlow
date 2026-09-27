import asyncio
from backend.app.storage.database import AsyncSessionLocal, BriefingModel
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(BriefingModel))
        rows = result.scalars().all()
        print(f"Total briefings in DB: {len(rows)}")
        for r in rows:
            print(f"- {r.category} (Generated at {r.generated_at})")
            print(f"Content: {r.content[:50]}...")

if __name__ == '__main__':
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check())
