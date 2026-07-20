"""No-output compatibility logger for extracted deterministic code.

Core never writes operational logs. Calls retained temporarily while classes
are mechanically extracted are routed to this stateless sink and will be
replaced by neutral result events where they carry semantic value.
"""

from typing import Any


class _NullLogger:
    __slots__ = ()

    def debug(self, *args: Any, **kwargs: Any) -> None:
        return None

    def info(self, *args: Any, **kwargs: Any) -> None:
        return None

    def warning(self, *args: Any, **kwargs: Any) -> None:
        return None

    warn = warning

    def error(self, *args: Any, **kwargs: Any) -> None:
        return None

    def exception(self, *args: Any, **kwargs: Any) -> None:
        return None


_NULL_LOGGER = _NullLogger()


def get_logger(_name: str = "") -> _NullLogger:
    """Return a stateless sink without importing a logging framework."""
    return _NULL_LOGGER

