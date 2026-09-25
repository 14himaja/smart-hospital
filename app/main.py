from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.api.auth import router as auth_router
from app.api.hospital import router as hospital_router
from app.api.chat import router as chat_router
from app.api.admin import router as admin_router
from app.api.voice_call import router as voice_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle startup and shutdown management."""
    try:
        from app.services.faiss_store import faiss_store
        from app.database import db
        if faiss_store.index is None or faiss_store.index.ntotal == 0:
            print("[Lifespan] FAISS index missing or empty. Auto-building from SQLite chunks...")
            faiss_store.rebuild(db.get_all_chunks_for_rebuild())
        else:
            print(f"[Lifespan] FAISS Vector Store active with {faiss_store.index.ntotal} vectors.")
    except Exception as e:
        print(f"[Lifespan Warning] FAISS store auto-init warning: {e}")

    print(f"[{settings.APP_NAME}] Server started successfully on http://{settings.HOST}:{settings.PORT}")
    print(f"[{settings.APP_NAME}] Web UI available at: http://{settings.HOST}:{settings.PORT}/")
    print(f"[{settings.APP_NAME}] API documentation at: http://{settings.HOST}:{settings.PORT}/docs")
    yield
    print(f"[{settings.APP_NAME}] Server shutting down...")


def create_app() -> FastAPI:
    """FastAPI Application Factory."""
    if not settings.SECRET_KEY or len(settings.SECRET_KEY) < 32:
        raise RuntimeError(
            "SECRET_KEY must be set (>= 32 random chars). "
            "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
        )

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Conversational Multi-Agent Healthcare Operations Assistant using Google ADK + FastAPI + MCP",
        lifespan=lifespan
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Mount Static Files (HTML, CSS, JS)
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Register Routers
    app.include_router(auth_router, prefix=settings.API_PREFIX)
    app.include_router(hospital_router, prefix=settings.API_PREFIX)
    app.include_router(chat_router, prefix=settings.API_PREFIX)
    app.include_router(admin_router, prefix=settings.API_PREFIX)
    app.include_router(voice_router)

    @app.get("/")
    async def root():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "operational",
            "docs": "/docs",
            "active_model": settings.MODEL_NAME
        }

    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}

    return app


app = create_app()
