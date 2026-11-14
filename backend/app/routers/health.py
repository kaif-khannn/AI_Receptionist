"""Liveness and readiness probes for hosting platforms and uptime monitors."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    """The process is up and serving requests."""
    return {"status": "ok"}


@router.get("/ready", response_model=None)
async def ready(request: Request) -> dict[str, str] | JSONResponse:
    """The database is reachable (if configured)."""
    db = getattr(request.app.state, "db", None)
    if db is None:
        return {"status": "ok", "database": "not_configured"}
    try:
        await db.ping()
    except Exception:
        return JSONResponse({"status": "unavailable", "database": "error"}, status_code=503)
    return {"status": "ok", "database": "ok"}
