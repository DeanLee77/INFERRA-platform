from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.adapters.inbound.http import api_router
from src.config import settings
from src.domain.exceptions import RuleValidationError
from src.infrastructure.auth_middleware import ApiKeyAuthMiddleware, assert_production_auth_config
from src.infrastructure.correlation_middleware import CorrelationIdMiddleware
from src.infrastructure.logging_config import configure_logging
from src.infrastructure.observability import configure_observability
from src.infrastructure.rate_limiter import RateLimitMiddleware
from src.infrastructure.secrets import redact_url

import structlog

configure_logging()

logger = structlog.get_logger("inferra.fastapi")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("starting_inferra_app", database_uri=redact_url(settings.SQLALCHEMY_DATABASE_URI))
    yield
    logger.info("stopping_inferra_app")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RuleValidationError)
    async def handle_rule_validation_error(_: Request, exc: RuleValidationError) -> JSONResponse:
        logger.warning("rule_validation_failed", rule_name=exc.rule_name, error_count=len(exc.errors))
        return JSONResponse(
            status_code=422,
            content=exc.to_dict(),
        )

    @app.exception_handler(ValueError)
    async def handle_value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Bad request", "detail": str(exc)},
        )

    @app.exception_handler(LookupError)
    async def handle_lookup_error(_: Request, exc: LookupError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Not found", "detail": str(exc)},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error": "Request validation failed",
                "details": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Internal server error"},
        )


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_csv_env(name: str) -> list[str]:
    value = os.environ.get(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def _cors_config() -> tuple[list[str], bool]:
    origins = _parse_csv_env("INFERRA_CORS_ALLOWED_ORIGINS")
    allow_credentials = _env_bool("INFERRA_CORS_ALLOW_CREDENTIALS", False)
    if "*" in origins and allow_credentials:
        allow_credentials = False
    if os.environ.get("INFERRA_ENV", "").strip().lower() in {"prod", "production"} and "*" in origins:
        raise RuntimeError("Production CORS requires explicit INFERRA_CORS_ALLOWED_ORIGINS; wildcard is not allowed")
    return origins, allow_credentials


def create_app() -> FastAPI:
    assert_production_auth_config()
    cors_origins, cors_allow_credentials = _cors_config()

    app = FastAPI(
        title="INFERRA Platform API",
        version="2.0.0",
        description="INFERRA Platform FastAPI application",
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(ApiKeyAuthMiddleware)
    app.add_middleware(RateLimitMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router)
    configure_observability(app)
    return app


app = create_app()
