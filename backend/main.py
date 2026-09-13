import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path

from config import get_settings

settings = get_settings()
logger   = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    #  Startup 
    logger.info("[startup] News App: initialising database & vector store")
    try:
        from backend.app.storage.database import init_db
        from backend.app.storage.qdrant_store import QdrantStore
        import asyncio

        # Initialize postgres database tables
        await init_db()

        # Run blocking Qdrant collection setup in a separate thread so it doesn't block the loop
        try:
            store = QdrantStore()
            await asyncio.to_thread(store.init_collection)
            logger.info("[startup] Qdrant collection initialized")
        except Exception as qd_err:
            logger.warning(
                f"[startup] Qdrant initialization failed (non-fatal): {qd_err}. "
                "The server will still run and serve cached data/Postgres, "
                "but vector search features may be unavailable."
            )

        # Start the pipeline scheduler
        from backend.app.scheduler.jobs import create_scheduler, run_pipeline
        scheduler = create_scheduler()
        scheduler.start()
        logger.info("[startup] Scheduler started")

        # Kick off an initial pipeline run immediately in the background
        asyncio.create_task(run_pipeline(trigger="startup"))

        logger.info("[startup] Ready")
    except Exception as e:
        logger.error(f"[startup] Initialisation failed: {e}")
        raise

    yield

    #  Shutdown 
    logger.info("[shutdown] Stopping scheduler")
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    logger.info("[shutdown] News App going offline")


app = FastAPI(
    title="News Application",
    description="AI-powered news aggregation and briefing API",
    version="1.0.0",
    lifespan=lifespan,
)

#  CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

#  API Routers 
from backend.app.api.routes.clusters  import router as clusters_router
from backend.app.api.routes.briefings import router as briefings_router
from backend.app.api.routes.dashboard import router as dashboard_router
from backend.app.api.routes.chat      import router as chat_router

app.include_router(clusters_router)
app.include_router(briefings_router)
app.include_router(dashboard_router)
app.include_router(chat_router)


#  Pipeline control endpoints 
@app.post("/api/pipeline/run", tags=["pipeline"])
async def trigger_pipeline():
    """Manually trigger a full pipeline run. Returns immediately with status."""
    import backend.app.scheduler.jobs as jobs
    if jobs._running:
        return {"status": "already_running", "message": "A pipeline run is already in progress."}
    import asyncio
    asyncio.create_task(jobs.run_pipeline(trigger="manual"))
    return {"status": "started", "message": "Pipeline run started in background."}


@app.get("/api/pipeline/status", tags=["pipeline"])
def pipeline_status():
    """Check whether a pipeline run is currently in progress."""
    import backend.app.scheduler.jobs as jobs
    return {"running": jobs._running}


#  Health check 
@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "healthy", "running": True}



