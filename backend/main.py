from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import get_settings
settings = get_settings()


@asynccontextmanager
async def lifespan(app:FastAPI):
    print(f"[startup] News App")

    yield
    print(f"[shutdown] going off...")

app = FastAPI(
    title = "News Application",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins = ["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"]
)

@app.get("/")
def health():
    return {
        "status": "healthy",
        "running": True
    }
