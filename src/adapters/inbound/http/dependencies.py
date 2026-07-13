"""
HTTP dependency-injection module.

Provides FastAPI dependencies (database session, settings, session store,
inference session service, rule repository) for inbound HTTP routes.
"""

from collections.abc import Generator
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.adapters.outbound.persistence.aegis_rule_repository import AegisRuleRepositoryImpl
from src.adapters.outbound.persistence.database import get_aegis_db, get_db
from src.adapters.outbound.persistence.rule_repository import RuleRepositoryImpl
from src.adapters.outbound.session.in_memory_session_store import InMemorySessionStore
from src.adapters.outbound.session.redis_session_store import RedisSessionStore
from src.adapters.outbound.llm.client import reset_llm_client
from src.adapters.outbound.llm.real_llm_orchestrator import reset_default_llm_circuit
from src.config import Settings, settings
from src.domain.inference.session_service import InferenceSessionService
from src.domain.state.feature_flags import get_feature_flags
from src.infrastructure.auth_middleware import has_scope
from src.ports.rule_repository_port import RuleRepositoryPort
from src.ports.session_store_port import SessionStorePort


def get_db_session() -> Generator[Session, None, None]:
    yield from get_db()


def get_aegis_db_session() -> Generator[Session, None, None]:
    yield from get_aegis_db()


def get_settings() -> Settings:
    return settings


def require_scope(required_scope: str):
    async def _dependency(request: Request) -> None:
        if not get_feature_flags().auth_enabled:
            return
        scopes = request.scope.get("inferra_auth_scopes") or ()
        if has_scope(scopes, required_scope):
            return
        raise HTTPException(
            status_code=403,
            detail=f"Missing required scope: {required_scope}",
        )

    return _dependency


@lru_cache()
def get_session_store() -> SessionStorePort:
    """
    Get the singleton session store instance.

    Uses in-memory storage by default. When INFERRA_REDIS_SESSION_STORE=true,
    returns a Redis-backed implementation for multi-worker deployments.
    """
    if get_feature_flags().redis_session_store:
        return RedisSessionStore()
    return InMemorySessionStore()


def get_inference_session_service(
    session_store: SessionStorePort = Depends(get_session_store)
) -> InferenceSessionService:
    """
    Get the inference session service instance.

    Singleton behaviour is inherited from get_session_store(),
    which is @lru_cache-decorated and returns the same SessionStorePort
    every call. InferenceSessionService itself is stateless (delegates
    to the store), so a fresh construction per call is safe and avoids
    the stale-closure / cross-session contamination risks of lru_cache
    on a dependency-injected function.
    """
    return InferenceSessionService(session_store)


def get_rule_repository(
    db: Session = Depends(get_db)
) -> RuleRepositoryPort:
    """
    Get a rule repository instance with database session.

    Request-scoped: each request gets its own database session.
    """
    return RuleRepositoryImpl(db)


def get_aegis_rule_repository(
    db: Session = Depends(get_aegis_db)
) -> RuleRepositoryPort:
    """
    Get an AEGIS rule repository instance with an AEGIS database session.

    Request-scoped: each request gets its own AEGIS database session and never
    falls back to the shared AXIOM/platform rule tables.
    """
    return AegisRuleRepositoryImpl(db)


def reset_singletons() -> None:
    """Reset all singleton caches. Use this in tests for clean state."""
    get_session_store.cache_clear()
    reset_llm_client()
    reset_default_llm_circuit()
