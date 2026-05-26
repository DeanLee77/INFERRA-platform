"""
Tests for SemanticCache.

Tests are designed to run without rdflib or Fuseki — they verify
eviction logic, OOM guard, delta queries, and graceful degradation.
"""

import time
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from src.adapters.outbound.ontology.semantic_cache import (
    SemanticCache,
    get_semantic_cache,
)

MODULE_PATH = "src.adapters.outbound.ontology.semantic_cache"


def _make_mock_rdflib():
    mock_module = MagicMock(name="rdflib")
    mock_graph = MagicMock(name="Graph")
    mock_graph.__len__ = MagicMock(return_value=0)
    mock_graph.add = MagicMock()
    mock_graph.remove = MagicMock()
    mock_graph.serialize = MagicMock(return_value="")
    mock_graph.__iter__ = MagicMock(return_value=iter([]))
    mock_module.Graph = MagicMock(return_value=mock_graph)
    mock_module.URIRef = MagicMock(side_effect=lambda x: x)
    return mock_module


def _rdflib_patch():
    return patch(f"{MODULE_PATH}.rdflib", _make_mock_rdflib())


def _rdflib_available_patch(enabled=True):
    return patch(f"{MODULE_PATH}.RDFLIB_AVAILABLE", enabled)


class TestSemanticCachePreload:
    def test_preload_skips_when_rdflib_unavailable(self):
        with _rdflib_available_patch(False):
            cache = SemanticCache()
            with patch(f"{MODULE_PATH}.FusekiAdapter") as mock_fa:
                cache.preload("rule1")
                mock_fa.get_rule_triples.assert_not_called()

    def test_preload_hit_on_duplicate(self):
        with _rdflib_available_patch(True), _rdflib_patch():
            cache = SemanticCache()
            with patch(f"{MODULE_PATH}.FusekiAdapter") as mock_fa:
                mock_fa.get_rule_triples.return_value = []
                cache.preload("rule1")
                cache.preload("rule1")
                assert mock_fa.get_rule_triples.call_count == 1
                assert cache._hit_count == 1

    def test_preload_miss_on_new_rule(self):
        with _rdflib_available_patch(True), _rdflib_patch():
            cache = SemanticCache()
            with patch(f"{MODULE_PATH}.FusekiAdapter") as mock_fa:
                mock_fa.get_rule_triples.return_value = []
                cache.preload("rule1")
                assert cache._miss_count == 1

    def test_preload_adds_triples_to_graph(self):
        with _rdflib_available_patch(True), _rdflib_patch():
            cache = SemanticCache()
            mock_graph = cache._graph
            mock_graph.__len__ = MagicMock(return_value=1)
            with patch(f"{MODULE_PATH}.FusekiAdapter") as mock_fa:
                mock_fa.get_rule_triples.return_value = [
                    ("http://s1", "http://p1", "http://o1"),
                ]
                cache.preload("rule1")
                assert cache.triple_count == 1

    def test_preload_records_load_timestamp(self):
        with _rdflib_available_patch(True), _rdflib_patch():
            cache = SemanticCache()
            with patch(f"{MODULE_PATH}.FusekiAdapter") as mock_fa:
                mock_fa.get_rule_triples.return_value = []
                cache.preload("rule1")
                assert "rule1" in cache._load_timestamps

    def test_triple_cap_triggers_eviction(self):
        with _rdflib_available_patch(True), _rdflib_patch():
            cache = SemanticCache()
            cache.MAX_TRIPLES = 2
            cache._graph.__len__ = MagicMock(return_value=3)
            with patch(f"{MODULE_PATH}.FusekiAdapter") as mock_fa:
                mock_fa.get_rule_triples.return_value = []
                with patch.object(cache, "_evict_oldest_entries") as mock_evict:
                    cache.preload("rule1")
                    mock_evict.assert_called_once_with(target=1)


class TestSemanticCacheEviction:
    def test_evict_oldest_entries(self):
        with _rdflib_available_patch(True), _rdflib_patch():
            cache = SemanticCache()
            cache._loaded_rules = {"rule1", "rule2"}
            cache._load_timestamps = {"rule1": 1.0, "rule2": 2.0}
            cache._graph.__len__ = MagicMock(
                side_effect=lambda: len(cache._loaded_rules) * 4
            )
            with patch.object(cache, "_rule_subgraph", return_value=[]):
                cache._evict_oldest_entries(target=5)
                assert len(cache._loaded_rules) == 1

    def test_eviction_removes_load_timestamps(self):
        with _rdflib_available_patch(True), _rdflib_patch():
            cache = SemanticCache()
            cache._loaded_rules = {"rule1"}
            cache._load_timestamps = {"rule1": 1.0}
            cache._graph.__len__ = MagicMock(return_value=10)
            with patch.object(cache, "_rule_subgraph", return_value=[]):
                cache._evict_oldest_entries(target=5)
                assert "rule1" not in cache._load_timestamps

    def test_evict_oldest_entries_ignores_remove_errors(self):
        with _rdflib_available_patch(True), _rdflib_patch():
            cache = SemanticCache()
            cache._loaded_rules = {"rule1"}
            cache._load_timestamps = {"rule1": 1.0}
            cache._graph.__len__ = MagicMock(
                side_effect=lambda: 10 if cache._loaded_rules else 0
            )
            cache._graph.remove.side_effect = Exception("remove failed")
            with patch.object(cache, "_rule_subgraph", return_value=[("s", "p", "o")]):
                cache._evict_oldest_entries(target=5)
            cache._graph.remove.assert_called_once_with(("s", "p", "o"))

    def test_evict_oldest_entries_noops_without_rdflib(self):
        with _rdflib_available_patch(False):
            cache = SemanticCache()
            cache._evict_oldest_entries(target=1)
            assert cache._graph is None

    def test_oom_guard_triggers_eviction(self):
        with _rdflib_available_patch(True), _rdflib_patch():
            cache = SemanticCache()
            cache.OOM_MEMORY_MB = 0.001
            with patch(f"{MODULE_PATH}.FusekiAdapter") as mock_fa:
                mock_fa.get_rule_triples.return_value = []
                with patch.object(
                    type(cache), "memory_usage_mb", new_callable=PropertyMock
                ) as mock_mem:
                    mock_mem.return_value = 500.0
                    with patch.object(cache, "_evict_oldest_entries") as mock_evict:
                        cache.preload("rule1")
                        mock_evict.assert_called()


class TestSemanticCacheDeltas:
    def test_query_deltas_returns_same_timestamp_as_empty(self):
        cache = SemanticCache()
        with patch(f"{MODULE_PATH}.FusekiAdapter") as mock_fa:
            result = cache.query_new_deltas(since_timestamp=0.0)
            assert result == []

    def test_query_deltas_delegates_to_fuseki(self):
        cache = SemanticCache()
        cache._last_query_timestamp = 0.0
        with patch(f"{MODULE_PATH}.FusekiAdapter") as mock_fa:
            mock_fa.query_deltas.return_value = [("s", "p", "o")]
            result = cache.query_new_deltas(since_timestamp=100.0)
            assert len(result) == 1
            assert cache._last_query_timestamp > 0

    def test_query_deltas_skips_when_timestamp_unchanged(self):
        cache = SemanticCache()
        ts = 100.0
        cache._last_query_timestamp = ts
        result = cache.query_new_deltas(since_timestamp=ts)
        assert result == []


class TestSemanticCacheProperties:
    def test_triple_count_without_rdflib(self):
        with _rdflib_available_patch(False):
            cache = SemanticCache()
            assert cache.triple_count == 0

    def test_memory_usage_without_rdflib(self):
        with _rdflib_available_patch(False):
            cache = SemanticCache()
            assert cache.memory_usage_mb == 0.0

    def test_memory_usage_returns_zero_when_serialization_fails(self):
        with _rdflib_available_patch(True), _rdflib_patch():
            cache = SemanticCache()
            cache._graph.serialize.side_effect = Exception("serialize failed")
            assert cache.memory_usage_mb == 0.0

    def test_hit_rate_no_accesses(self):
        cache = SemanticCache()
        assert cache.hit_rate == 0.0

    def test_hit_rate_with_hits_and_misses(self):
        cache = SemanticCache()
        cache._hit_count = 3
        cache._miss_count = 1
        assert cache.hit_rate == 0.75


class TestSemanticCacheClear:
    def test_clear_resets_state(self):
        with _rdflib_available_patch(True), _rdflib_patch():
            cache = SemanticCache()
            cache._loaded_rules = {"rule1"}
            cache._hit_count = 5
            cache._miss_count = 3
            cache.clear()
            assert len(cache._loaded_rules) == 0
            assert cache._hit_count == 0
            assert cache._miss_count == 0
            assert cache.triple_count == 0

    def test_clear_without_rdflib(self):
        with _rdflib_available_patch(False):
            cache = SemanticCache()
            cache._loaded_rules = {"rule1"}
            cache.clear()
            assert len(cache._loaded_rules) == 0
            assert cache._graph is None


class TestGetSemanticCache:
    def test_returns_singleton(self):
        with patch(f"{MODULE_PATH}._cache_instance", None):
            cache1 = get_semantic_cache()
            cache2 = get_semantic_cache()
            assert cache1 is cache2


class TestSemanticCacheRuleSubgraph:
    def test_rule_subgraph_filters_by_sanitized_rule_prefix(self):
        with _rdflib_available_patch(True), _rdflib_patch():
            cache = SemanticCache()
            cache._graph.__iter__ = MagicMock(
                return_value=iter(
                    [
                        (
                            "http://inferra.ai/schema#rule/benefit_rule/node1",
                            "p",
                            "o",
                        ),
                        ("http://other/rule", "p", "o"),
                    ]
                )
            )

            result = cache._rule_subgraph("benefit rule")

        assert result == [
            ("http://inferra.ai/schema#rule/benefit_rule/node1", "p", "o")
        ]

    def test_rule_subgraph_returns_empty_without_rdflib(self):
        with _rdflib_available_patch(False):
            cache = SemanticCache()
            assert cache._rule_subgraph("rule") == []


def test_sanitize_uri_replaces_unsafe_characters():
    from src.adapters.outbound.ontology.semantic_cache import _sanitize_uri

    assert _sanitize_uri("A rule/name!") == "A_rule_name_"
