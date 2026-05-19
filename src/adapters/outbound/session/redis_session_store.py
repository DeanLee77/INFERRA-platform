"""
Redis-backed inference session store.

This adapter is intended for trusted INFERRA deployments where session objects
are created by the backend and stored in an internal Redis instance. It uses a
small versioned pickle envelope so the existing rich InferenceSession object can
survive across workers without flattening the whole inference engine state into
a lossy JSON schema.
"""

from __future__ import annotations

import os
import pickle
import threading
from contextlib import nullcontext
from datetime import datetime, timedelta
from typing import List, Optional

from src.domain.exceptions import ConcurrentModificationError
from src.domain.inference.session import InferenceSession
from src.ports.session_store_port import SessionStorePort
from src.infrastructure.logging_config import get_logger
from src.infrastructure.secrets import redis_url_from_env

_logger = get_logger(__name__)


class RedisSessionStore(SessionStorePort):
    """Redis implementation of SessionStorePort with TTL refresh on access."""

    ENVELOPE_VERSION = 1
    DEFAULT_URL = "redis://localhost:6379/0"
    DEFAULT_NAMESPACE = "inferra:session"
    DEFAULT_TTL_SECONDS = 3600

    def __init__(
        self,
        redis_url: Optional[str] = None,
        *,
        namespace: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        redis_client=None,
        ping_on_init: bool = True,
    ) -> None:
        self._namespace = (namespace or os.environ.get("INFERRA_REDIS_SESSION_NAMESPACE") or self.DEFAULT_NAMESPACE).rstrip(":")
        self._ttl_seconds = int(
            ttl_seconds
            if ttl_seconds is not None
            else os.environ.get("INFERRA_SESSION_TTL_SECONDS", self.DEFAULT_TTL_SECONDS)
        )
        self._lock = threading.RLock()
        if redis_client is not None:
            self._redis = redis_client
        else:
            import redis

            self._redis = redis.Redis.from_url(
                redis_url or redis_url_from_env("REDIS_URL", self.DEFAULT_URL, 0)
            )
        if ping_on_init:
            self._redis.ping()
        _logger.info(
            f"RedisSessionStore initialized (namespace={self._namespace}, ttl={self._ttl_seconds}s)"
        )

    def get(self, session_id: str) -> Optional[InferenceSession]:
        with self._lock:
            payload = self._redis.get(self._key(session_id))
            if payload is None:
                return None
            try:
                session = self._decode(payload)
            except Exception:
                _logger.warning(f"Corrupt Redis session payload removed: {session_id}")
                self._redis.delete(self._key(session_id))
                return None
            session.touch()
            self._write(session)
            return session

    def save(self, session: InferenceSession) -> None:
        if not session or not session.session_id:
            raise ValueError("Session must have a valid session_id")
        with self._lock, self._distributed_lock(session.session_id):
            key = self._key(session.session_id)
            current_payload = self._redis.get(key)
            if current_payload is not None:
                current_session = self._decode(current_payload)
                current_version = int(getattr(current_session, "version", 0))
                incoming_version = int(getattr(session, "version", 0))
                if incoming_version != current_version:
                    raise ConcurrentModificationError(
                        f"Session {session.session_id} was modified by another writer "
                        f"(expected version {incoming_version}, found {current_version})"
                    )
                session.version = current_version + 1
            else:
                session.version = max(int(getattr(session, "version", 0)), 0)
            self._write(session)
            _logger.info(
                f"Session saved to Redis: {session.session_id} "
                f"(rule={session.rule_name}, target={session.target_node_name})"
            )

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return bool(self._redis.delete(self._key(session_id)))

    def exists(self, session_id: str) -> bool:
        with self._lock:
            return bool(self._redis.exists(self._key(session_id)))

    def list_sessions(self) -> List[str]:
        prefix = f"{self._namespace}:"
        with self._lock:
            return sorted(
                key.decode("utf-8").removeprefix(prefix)
                if isinstance(key, bytes)
                else str(key).removeprefix(prefix)
                for key in self._redis.scan_iter(match=f"{prefix}*")
            )

    def clear_expired(self, max_age_seconds: int) -> int:
        cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
        cleared = 0
        with self._lock:
            for key in list(self._redis.scan_iter(match=f"{self._namespace}:*")):
                payload = self._redis.get(key)
                if payload is None:
                    continue
                try:
                    session = self._decode(payload)
                except Exception:
                    self._redis.delete(key)
                    cleared += 1
                    continue
                if session.last_accessed < cutoff:
                    cleared += int(bool(self._redis.delete(key)))
        if cleared:
            _logger.info(f"Cleared {cleared} expired Redis sessions")
        return cleared

    def clear_all(self) -> None:
        with self._lock:
            for key in list(self._redis.scan_iter(match=f"{self._namespace}:*")):
                self._redis.delete(key)

    def count(self) -> int:
        return len(self.list_sessions())

    def _key(self, session_id: str) -> str:
        return f"{self._namespace}:{session_id}"

    def _write(self, session: InferenceSession) -> None:
        self._redis.set(
            self._key(session.session_id),
            self._encode(session),
            ex=self._ttl_seconds,
        )

    def _distributed_lock(self, session_id: str):
        if hasattr(self._redis, "lock"):
            return self._redis.lock(
                f"{self._namespace}:lock:{session_id}",
                timeout=5,
                blocking_timeout=5,
                thread_local=True,
            )
        return nullcontext()

    def _encode(self, session: InferenceSession) -> bytes:
        return pickle.dumps(
            {
                "version": self.ENVELOPE_VERSION,
                "session": session,
            },
            protocol=pickle.HIGHEST_PROTOCOL,
        )

    def _decode(self, payload: bytes) -> InferenceSession:
        envelope = pickle.loads(payload)
        if not isinstance(envelope, dict) or envelope.get("version") != self.ENVELOPE_VERSION:
            raise ValueError("Unsupported Redis session envelope")
        session = envelope.get("session")
        if not isinstance(session, InferenceSession):
            raise ValueError("Redis payload did not contain an InferenceSession")
        return session
