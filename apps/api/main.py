from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from apps.api.middleware import CorrelationIdMiddleware
from apps.api.routers import agents, analytics, auth, intelligence, reports, suppliers
from procureai.config.logging import configure_logging
from procureai.config.settings import get_settings
from procureai.db.session import engine

settings = get_settings()
configure_logging()
app = FastAPI(
    title=settings.app_name, version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json"
)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(suppliers.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(intelligence.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")


@app.get("/health", tags=["operations"])
def health():
    return {"status": "ok", "service": settings.app_name, "demo_mode": settings.demo_mode}


@app.get("/ready", tags=["operations"])
def readiness():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "Unexpected server error",
            "details": {},
            "correlation_id": getattr(request.state, "correlation_id", "unknown"),
        },
    )
