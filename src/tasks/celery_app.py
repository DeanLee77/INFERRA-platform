"""
Celery application for INFERRA async sync pipeline.

Configured with Redis broker and result backend. Tasks are gated behind
the ASYNC_SYNC_ENABLED feature flag — the publisher checks the flag
before submitting tasks to the queue.

Rate limiting: per-task rate limit of 10/m prevents overwhelming Fuseki
on bulk rule saves. Submission-level idempotency skips duplicate tasks.
"""

from src.infrastructure.environment import load_process_environment

load_process_environment()

from src.domain.state.feature_flags import (
    build_effective_feature_flag_report,
    get_feature_flags,
    validate_runtime_feature_flags,
)
from src.infrastructure.secrets import redis_url_from_env

import structlog

_worker_flags = validate_runtime_feature_flags(get_feature_flags())
structlog.get_logger("inferra.celery").info(
    "feature_flag_snapshot",
    **build_effective_feature_flag_report("worker", flags=_worker_flags),
)

TASK_MODULES = (
    "src.tasks.rule_sync",
    "src.tasks.ontology_post_reasoner",
    "src.tasks.induction",
)

try:
    from celery import Celery

    app = Celery(
        "inferra",
        broker=redis_url_from_env("CELERY_BROKER_URL", "redis://localhost:6379/0", 0),
        backend=redis_url_from_env("CELERY_RESULT_BACKEND", "redis://localhost:6379/1", 1),
        include=TASK_MODULES,
    )

    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        imports=TASK_MODULES,
    )

    CELERY_AVAILABLE = True
except ImportError:  # pragma: no cover
    CELERY_AVAILABLE = False

    class _StubCelery:
        """Stub when celery is not installed — tasks become no-ops."""

        def task(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

    app = _StubCelery()
