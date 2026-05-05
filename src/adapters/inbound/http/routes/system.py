"""
System API Router.
Handles system-level endpoints like health checks and root info.

Phase 1 WS-5: Enhanced health check with component-level status
(database connectivity, redis placeholder, graph_init flag).

Phase 2: Extended health check with Celery, Fuseki, and SemanticCache stats.
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

import structlog

from src.adapters.inbound.http.dependencies import get_db_session

router = APIRouter(tags=["system"])
logger = structlog.get_logger("inferra.fastapi.system")


class HealthResponse(BaseModel):
    """Response model for health check endpoints."""
    status: str = Field(..., description="Overall service status")
    version: str = Field(..., description="Service version")
    components: dict = Field(default_factory=dict, description="Component-level status")


class LivenessResponse(BaseModel):
    """Fast process-level liveness response."""
    status: str = Field(..., description="Process liveness status")
    version: str = Field(..., description="Service version")


def _check_redis() -> str:
    try:
        import redis
        redis_url = os.environ.get("REDIS_URL")
        r = redis.Redis.from_url(redis_url) if redis_url else redis.Redis()
        r.ping()
        return "ok"
    except Exception:
        return "unavailable"


def _check_celery() -> str:
    try:
        from src.tasks.celery_app import CELERY_AVAILABLE, app
        if not CELERY_AVAILABLE:
            return "not_configured"
        insp = app.control.inspect(timeout=1.0)
        result = insp.ping()
        return "ok" if result else "unavailable"
    except Exception:
        return "unavailable"


def _check_fuseki() -> str:
    try:
        from src.adapters.outbound.ontology.fuseki_adapter import FusekiAdapter
        FusekiAdapter.health_check()
        return "ok"
    except ImportError:
        return "not_configured"
    except Exception:
        logger.warning("fuseki_health_check_failed")
        return "unavailable"


def _get_semantic_cache_stats() -> dict:
    try:
        from src.adapters.outbound.ontology.semantic_cache import get_semantic_cache
        cache = get_semantic_cache()
        return {
            "triples": cache.triple_count,
            "memory_mb": round(cache.memory_usage_mb, 1),
            "hit_rate": round(cache.hit_rate, 2),
        }
    except Exception:
        return {"triples": 0, "memory_mb": 0.0, "hit_rate": 0.0}


def _check_z3_solver() -> str:
    try:
        import z3
        solver = z3.Solver()
        solver.set("timeout", 500)
        solver.check()
        return "ok"
    except ImportError:
        logger.warning("z3_solver_not_installed")
        return "unavailable"
    except Exception:
        logger.warning("z3_solver_health_check_failed", exc_info=True)
        return "unavailable"


def _get_induction_worker_status() -> dict:
    try:
        from src.tasks.celery_app import CELERY_AVAILABLE, app
        if not CELERY_AVAILABLE:
            return {"status": "not_configured", "active": 0, "pending_jobs": 0}
        insp = app.control.inspect(timeout=1.0)
        active = insp.active() or {}
        reserved = insp.reserved() or {}
        return {
            "status": "ok",
            "active": sum(len(v) for v in active.values()),
            "pending_jobs": sum(len(v) for v in reserved.values()),
        }
    except Exception:
        logger.warning("induction_worker_health_check_failed", exc_info=True)
        return {"status": "unavailable", "active": 0, "pending_jobs": 0}


def _get_active_session_count() -> int:
    try:
        from src.dependencies import get_session_store
        store = get_session_store()
        if hasattr(store, "count"):
            return int(store.count())
        return len(store.list_sessions())
    except Exception:
        logger.warning("active_session_count_failed", exc_info=True)
        return 0


@router.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "INFERRA-PyRest",
        "framework": "FastAPI",
        "status": "running",
    }


@router.get("/live", response_model=LivenessResponse)
async def live_check() -> LivenessResponse:
    """Fast liveness probe that does not call external dependencies."""
    return LivenessResponse(status="ok", version="2.0.0")


@router.get("/api/v1/live", response_model=LivenessResponse)
async def live_check_v1() -> LivenessResponse:
    """API v1 liveness probe."""
    return await live_check()


@router.get("/health", response_model=HealthResponse)
async def health_check(db: Optional[Session] = Depends(get_db_session)) -> HealthResponse:
    """
    Health check endpoint.

    Returns the status of the service and its components:
    - database: PostgreSQL connectivity
    - redis: Redis connectivity
    - celery: Celery worker availability
    - fuseki: Fuseki SPARQL endpoint reachability
    - graph_init: whether the dependency graph has been initialized
    - semantic_cache: triple count, memory usage, hit rate
    """
    components: dict = {
        "redis": _check_redis(),
        "celery": _check_celery(),
        "fuseki": _check_fuseki(),
        "graph_init": True,
        "semantic_cache": _get_semantic_cache_stats(),
        "active_sessions": _get_active_session_count(),
        "z3_solver": _check_z3_solver(),
        "induction_workers": _get_induction_worker_status(),
    }

    db_status = "ok"
    try:
        if db is not None:
            db.execute(text("SELECT 1"))
        else:
            db_status = "not_configured"
    except Exception:
        logger.warning("health_check_db_unavailable", exc_info=True)
        db_status = "unavailable"
    components["database"] = db_status

    critical_statuses = {components["database"], components["redis"]}
    optional_statuses = {
        components["celery"],
        components["fuseki"],
        components["z3_solver"],
        components["induction_workers"]["status"],
    }

    if db_status == "ok" and components["redis"] in ("ok", "not_configured"):
        overall = "ok"
    elif any(s == "unavailable" for s in critical_statuses):
        overall = "unhealthy"
    else:
        overall = "degraded"

    if any(s == "unavailable" for s in optional_statuses):
        overall = "degraded" if overall == "ok" else overall

    return HealthResponse(
        status=overall,
        version="2.0.0",
        components=components,
    )


@router.get("/api/v1/health", response_model=HealthResponse)
async def health_check_v1(db: Optional[Session] = Depends(get_db_session)) -> HealthResponse:
    """
    API v1 health check endpoint (canonical path under /api/v1/).

    Delegates to the root health check for consistent response shape.
    """
    return await health_check(db)
