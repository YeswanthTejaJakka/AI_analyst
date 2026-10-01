"""
QueryPilot — AI-powered natural-language database analyst.
FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.database import router as database_router
from app.core.config import settings

# Configure logging — never log credentials
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("querypilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("QueryPilot starting up...")
    logger.info(f"LLM Provider: {settings.LLM_PROVIDER}")
    logger.info(f"Sample DB Path: {settings.SAMPLE_DB_PATH}")
    yield
    logger.info("QueryPilot shutting down...")


app = FastAPI(
    title="QueryPilot API",
    description=(
        "AI-powered natural-language database analyst. "
        "Query databases using plain English with ambiguity detection, "
        "clarification questions, and safe SQL execution."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(database_router)
app.include_router(chat_router)


# --- Root Endpoints ---

@app.get("/", tags=["Health"])
async def root():
    return {
        "app": "QueryPilot",
        "version": "1.0.0",
        "status": "running",
        "description": "AI-powered natural-language database analyst",
    }


@app.get("/api/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "llm_provider": settings.LLM_PROVIDER,
    }
