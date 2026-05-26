"""
Celery application for INFERRA async sync pipeline.

Configured with Redis broker and result backend. Tasks are gated behind
the ASYNC_SYNC_ENABLED feature flag — the publisher checks the flag
before submitting tasks to the queue.

Rate limiting: per-task rate limit of 10/m prevents overwhelming Fuseki
on bulk rule saves. Submission-level idempotency skips duplicate tasks.
"""

from src.infrastructure.secrets import redis_url_from_env

try:
    from celery import Celery

    app = Celery(
        "inferra",
        broker=redis_url_from_env("CELERY_BROKER_URL", "redis://localhost:6379/0", 0),
        backend=redis_url_from_env("CELERY_RESULT_BACKEND", "redis://localhost:6379/1", 1),
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
    )

    app.autodiscover_tasks(["src.tasks"])

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
