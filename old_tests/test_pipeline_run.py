import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.abspath("."))

from backend.app.scheduler.jobs import run_pipeline
from backend.app.storage.database import init_db

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    result = await run_pipeline(trigger="manual")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
