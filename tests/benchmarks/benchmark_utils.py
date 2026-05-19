"""Helpers for stable benchmark regression tests."""

import importlib
import io
import logging
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from typing import Iterable, Iterator, Tuple

import structlog


class _NullLogger:
    """Minimal logger that accepts stdlib and structlog-style calls."""

    def bind(self, *args, **kwargs):
        return self

    def new(self, *args, **kwargs):
        return self

    def unbind(self, *args, **kwargs):
        return self

    def try_unbind(self, *args, **kwargs):
        return self

    def __getattr__(self, name):
        return self._noop

    @staticmethod
    def _noop(*args, **kwargs):
        return None


def _drop_structlog_event(logger, method_name, event_dict):
    raise structlog.DropEvent


@contextmanager
def quiet_benchmark_logging(
    module_logger_attrs: Iterable[Tuple[str, str]] = (),
) -> Iterator[None]:
    """
    Disable log I/O and high-frequency module loggers while timing benchmarks.

    Regression benchmarks should measure algorithmic work, not terminal/file
    throughput. This helper also handles unconfigured structlog, whose default
    logger writes directly to stdout.
    """
    previous_disable_level = logging.root.manager.disable
    previous_structlog_config = structlog.get_config()
    sink = io.StringIO()
    null_logger = _NullLogger()
    patched = []

    try:
        logging.disable(logging.CRITICAL)
        structlog.configure(
            processors=[_drop_structlog_event],
            context_class=dict,
            wrapper_class=structlog.BoundLogger,
            logger_factory=structlog.ReturnLoggerFactory(),
            cache_logger_on_first_use=False,
        )

        for module_name, attr_name in module_logger_attrs:
            module = importlib.import_module(module_name)
            patched.append((module, attr_name, getattr(module, attr_name)))
            setattr(module, attr_name, null_logger)

        with redirect_stdout(sink), redirect_stderr(sink):
            yield
    finally:
        for module, attr_name, original in reversed(patched):
            setattr(module, attr_name, original)
        structlog.configure(**previous_structlog_config)
        logging.disable(previous_disable_level)
