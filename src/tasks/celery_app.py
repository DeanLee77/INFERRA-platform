"""
Celery application for INFERRA async sync pipeline.

Configured with Redis broker and result backend. Tasks are gated behind
the ASYNC_SYNC_ENABLED feature flag — the publisher checks the flag
before submitting tasks to the queue.

Rate limiting: per-task rate limit of 10/m prevents overwhelming Fuseki
on bulk rule saves. Submission-level idempotency skips duplicate tasks.
"""

import os

try:
    from celery import Celery

    app = Celery(
        "inferra",
        broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
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
