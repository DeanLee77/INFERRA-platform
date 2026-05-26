"""
Semantic Cache — in-memory RDFLib cache for ontology triples.

Eliminates Fuseki from the hot execution path. Preloads rule triples
at session start, queries deltas post-reasoning only. Includes eviction,
OOM guard, and observability metrics.

When rdflib is not installed, the cache degrades gracefully — preload
and query operations become no-ops, and all reads fall through to
direct Fuseki queries.
"""

import sys
import time
from typing import List, Optional, Set, Tuple

import structlog

try:
    import rdflib

    RDFLIB_AVAILABLE = True
except ImportError:
    rdflib = None
    RDFLIB_AVAILABLE = False

from src.adapters.outbound.ontology.fuseki_adapter import FusekiAdapter

log = structlog.get_logger()


class SemanticCache:
    """
    In-memory RDFLib semantic cache with eviction and OOM guard.

    Preloads triples for rules at session start. Queries deltas from
    Fuseki post-reasoning. Evicts oldest entries when approaching
    memory limits. Falls back to direct Fuseki queries on cache miss.
    """

    MAX_TRIPLES = 500_000
    OOM_MEMORY_MB = 200

    def __init__(self):
        if RDFLIB_AVAILABLE:
            self._graph = rdflib.Graph()
        else:
            self._graph = None
        self._loaded_rules: Set[str] = set()
        self._last_query_timestamp: float = 0.0
        self._hit_count: int = 0
        self._miss_count: int = 0
        self._load_timestamps: dict = {}

    def preload(self, rule_name: str) -> None:
        """
        Preload triples for a rule. Skips if already loaded. Evicts if near OOM.

        Args:
            rule_name: Name of the rule to preload
        """
        if not RDFLIB_AVAILABLE:
            log.debug("semantic_cache_skip_rdflib_unavailable", rule_name=rule_name)
            return

        if rule_name in self._loaded_rules:
            self._hit_count += 1
            log.info("semantic_cache_hit", rule_name=rule_name)
            return

        if self.memory_usage_mb > self.OOM_MEMORY_MB:
            log.warning(
                "semantic_cache_near_oom",
                memory_mb=self.memory_usage_mb,
                triple_count=len(self._graph),
            )
            self._evict_oldest_entries(target=self.MAX_TRIPLES // 2)

        if len(self._graph) > self.MAX_TRIPLES:
            log.warning(
                "semantic_cache_triple_cap",
                triple_count=len(self._graph),
            )
            self._evict_oldest_entries(target=self.MAX_TRIPLES // 2)

        self._miss_count += 1
        triples = FusekiAdapter.get_rule_triples(rule_name)
        for s, p, o in triples:
            self._graph.add(
                (rdflib.URIRef(s), rdflib.URIRef(p), rdflib.URIRef(o))
            )
        self._loaded_rules.add(rule_name)
        self._load_timestamps[rule_name] = time.time()
        log.info(
            "semantic_cache_preload",
            rule_name=rule_name,
            triple_count=len(self._graph),
            memory_mb=self.memory_usage_mb,
        )

    def query_new_deltas(self, since_timestamp: float) -> List[Tuple]:
        """
        Return triples not previously injected since the given timestamp.

        Args:
            since_timestamp: Unix epoch seconds

        Returns:
            List of (subject, predicate, object) tuples
        """
        if since_timestamp == self._last_query_timestamp:
            return []
        deltas = FusekiAdapter.query_deltas(since_timestamp)
        self._last_query_timestamp = time.time()
        log.info(
            "semantic_cache_deltas",
            delta_count=len(deltas),
            since=since_timestamp,
        )
        return deltas

    def _evict_oldest_entries(self, target: int) -> None:
        """
        Evict oldest preloaded rules until triple count is below target.

        Args:
            target: Target triple count to evict down to
        """
        if not RDFLIB_AVAILABLE or self._graph is None:
            return

        while len(self._graph) > target and self._loaded_rules:
            oldest = next(iter(self._loaded_rules))
            self._loaded_rules.discard(oldest)
            self._load_timestamps.pop(oldest, None)
            subgraph = self._rule_subgraph(oldest)
            for triple in subgraph:
                try:
                    self._graph.remove(triple)
                except Exception:
                    pass
            log.info(
                "semantic_cache_evicted",
                rule_name=oldest,
                triple_count=len(self._graph),
            )

    def _rule_subgraph(self, rule_name: str) -> List[Tuple]:
        """
        Extract triples associated with a rule by subject URI pattern.

        Args:
            rule_name: Rule name to match

        Returns:
            List of (subject, predicate, object) tuples
        """
        if not RDFLIB_AVAILABLE or self._graph is None:
            return []
        rule_uri_prefix = f"http://inferra.ai/schema#rule/{_sanitize_uri(rule_name)}"
        return [
            (str(s), str(p), str(o))
            for s, p, o in self._graph
            if str(s).startswith(rule_uri_prefix)
        ]

    def clear(self) -> None:
        """Clear all cached data. Called on session teardown to prevent RDFLib leaks."""
        if RDFLIB_AVAILABLE:
            self._graph = rdflib.Graph()
        else:
            self._graph = None
        self._loaded_rules.clear()
        self._load_timestamps.clear()
        self._last_query_timestamp = 0.0
        self._hit_count = 0
        self._miss_count = 0
        log.info("semantic_cache_cleared")

    @property
    def triple_count(self) -> int:
        return len(self._graph) if self._graph is not None else 0

    @property
    def memory_usage_mb(self) -> float:
        if not RDFLIB_AVAILABLE or self._graph is None:
            return 0.0
        try:
            serialized = self._graph.serialize(format="nt")
            return sys.getsizeof(serialized) / (1024 * 1024)
        except Exception:
            return 0.0

    @property
    def hit_rate(self) -> float:
        total = self._hit_count + self._miss_count
        return self._hit_count / total if total > 0 else 0.0


def _sanitize_uri(name: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", name)


_cache_instance: Optional[SemanticCache] = None


def get_semantic_cache() -> SemanticCache:
    """Get the global semantic cache instance (singleton per process)."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SemanticCache()
    return _cache_instance
