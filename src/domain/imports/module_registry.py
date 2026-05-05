"""
ModuleRegistry — LRU + TTL + size-bounded cache for parsed rule modules.

Caches parsed NodeSet objects by (rule_name, content_hash) with:
- LRU eviction when maxsize is reached
- TTL-based expiration (600s default)
- Invalidation on RuleUpdated events
- Transitive invalidation (evicts stale caches that depend on updated modules)

Gated by MODULAR_IMPORTS feature flag — when disabled, all operations
are no-ops and the registry appears empty.
"""

import hashlib
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

import structlog

from src.domain.state.feature_flags import FeatureFlags

log = structlog.get_logger()

DEFAULT_MAX_SIZE = 256
DEFAULT_TTL_S = 600


class _CacheEntry:
    __slots__ = ("value", "expires_at", "dependencies")

    def __init__(self, value: Any, expires_at: float, dependencies: Optional[set] = None):
        self.value = value
        self.expires_at = expires_at
        self.dependencies = dependencies or set()


class ModuleRegistry:
    """
    LRU + TTL + size-bounded cache for parsed rule modules.

    Stores parsed module outputs keyed by (rule_name, content_hash).
    Evicts least-recently-used entries when at capacity. Expired
    entries are lazily removed on access.

    Args:
        max_size: Maximum number of cached entries (default: 256)
        ttl_seconds: Time-to-live per entry in seconds (default: 600)
        feature_flags: Optional FeatureFlags snapshot (uses default if None)
    """

    def __init__(
        self,
        max_size: int = DEFAULT_MAX_SIZE,
        ttl_seconds: float = DEFAULT_TTL_S,
        feature_flags: Optional[FeatureFlags] = None,
    ):
        self._max_size = max(1, max_size)
        self._ttl_seconds = ttl_seconds
        self._feature_flags = feature_flags or FeatureFlags()
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._reverse_deps: Dict[str, set] = {}
        self._hit_count: int = 0
        self._miss_count: int = 0

    @staticmethod
    def make_key(rule_name: str, content_hash: str) -> str:
        """Create a composite cache key from rule name and content hash."""
        return f"{rule_name}:{content_hash}"

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute SHA-256 hash of rule content for cache keying."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def get(self, rule_name: str, content_hash: str) -> Optional[Any]:
        """
        Retrieve a cached module by (rule_name, content_hash).

        On hit, moves the entry to the end of the LRU (most recently used).
        On miss or expired entry, returns None and removes stale entries.

        Args:
            rule_name: Name of the rule module
            content_hash: Content hash for versioning

        Returns:
            Cached value if found and not expired, None otherwise
        """
        if not self._feature_flags.modular_imports:
            return None

        key = self.make_key(rule_name, content_hash)
        entry = self._cache.get(key)

        if entry is None:
            self._miss_count += 1
            return None

        if time.time() > entry.expires_at:
            self._remove_entry(key)
            self._miss_count += 1
            log.debug("module_registry_expired", key=key)
            return None

        self._cache.move_to_end(key)
        self._hit_count += 1
        log.debug("module_registry_hit", key=key)
        return entry.value

    def put(
        self,
        rule_name: str,
        content_hash: str,
        value: Any,
        dependencies: Optional[set] = None,
    ) -> None:
        """
        Store a parsed module in the cache.

        If the cache is at capacity, evicts the least-recently-used entry.
        Updates reverse dependency index for transitive invalidation.

        Args:
            rule_name: Name of the rule module
            content_hash: Content hash for versioning
            value: Parsed module output to cache
            dependencies: Set of rule names this module depends on
        """
        if not self._feature_flags.modular_imports:
            return

        key = self.make_key(rule_name, content_hash)
        expires_at = time.time() + self._ttl_seconds

        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key].expires_at = expires_at
            self._cache[key].value = value
            self._cache[key].dependencies = dependencies or set()
        else:
            if len(self._cache) >= self._max_size:
                self._evict_lru()
            self._cache[key] = _CacheEntry(value, expires_at, dependencies or set())

        if dependencies:
            for dep in dependencies:
                if dep not in self._reverse_deps:
                    self._reverse_deps[dep] = set()
                self._reverse_deps[dep].add(key)

        log.debug(
            "module_registry_put",
            key=key,
            cache_size=len(self._cache),
            max_size=self._max_size,
        )

    def invalidate(self, rule_name: str) -> int:
        """
        Invalidate all cache entries for a rule and its transitive dependents.

        Removes entries keyed by rule_name (any hash) and entries that
        list rule_name in their dependencies (reverse deps).

        Args:
            rule_name: Name of the rule to invalidate

        Returns:
            Number of entries invalidated
        """
        if not self._feature_flags.modular_imports:
            return 0

        keys_to_remove = set()

        for key in list(self._cache.keys()):
            if key.startswith(f"{rule_name}:"):
                keys_to_remove.add(key)

        transitive = self._reverse_deps.pop(rule_name, set())
        keys_to_remove.update(transitive)

        for key in keys_to_remove:
            self._remove_entry(key)

        log.info(
            "module_registry_invalidated",
            rule_name=rule_name,
            entries_removed=len(keys_to_remove),
        )
        return len(keys_to_remove)

    def clear(self) -> None:
        """Clear all cached entries and reverse dependency index."""
        self._cache.clear()
        self._reverse_deps.clear()
        self._hit_count = 0
        self._miss_count = 0
        log.info("module_registry_cleared")

    def _evict_lru(self) -> None:
        """Evict the least-recently-used entry."""
        if self._cache:
            key, _ = self._cache.popitem(last=False)
            for dep_set in self._reverse_deps.values():
                dep_set.discard(key)
            log.debug("module_registry_lru_evicted", key=key)

    def _remove_entry(self, key: str) -> None:
        """Remove a single entry and clean up reverse deps."""
        self._cache.pop(key, None)
        for dep_set in self._reverse_deps.values():
            dep_set.discard(key)

    @property
    def size(self) -> int:
        """Current number of cached entries."""
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0.0 to 1.0)."""
        total = self._hit_count + self._miss_count
        return self._hit_count / total if total > 0 else 0.0

    @property
    def max_size(self) -> int:
        return self._max_size

    @property
    def ttl_seconds(self) -> float:
        return self._ttl_seconds
