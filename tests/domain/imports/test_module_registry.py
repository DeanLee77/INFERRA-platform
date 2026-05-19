"""Tests for ModuleRegistry — LRU, TTL, size bounds, invalidation, hit rate."""

import time
from unittest.mock import MagicMock

import pytest

from src.domain.imports.module_registry import ModuleRegistry
from src.domain.state.feature_flags import FeatureFlags


def _make_flags(modular_imports=True, **overrides):
    defaults = {
        "use_hypergraph": False,
        "legacy_iterate": True,
        "layered_memory": True,
        "ml_optimized_dfs": False,
        "async_sync_enabled": False,
        "modular_imports": modular_imports,
    }
    defaults.update(overrides)
    return FeatureFlags(**defaults)


class TestModuleRegistryGetPut:
    def test_put_and_get(self):
        reg = ModuleRegistry(feature_flags=_make_flags())
        reg.put("rule1", "hash1", {"data": "value"})
        assert reg.get("rule1", "hash1") == {"data": "value"}

    def test_get_miss(self):
        reg = ModuleRegistry(feature_flags=_make_flags())
        assert reg.get("rule1", "hash1") is None

    def test_put_overwrites_existing_key(self):
        reg = ModuleRegistry(feature_flags=_make_flags())
        reg.put("rule1", "hash1", "v1")
        reg.put("rule1", "hash1", "v2")
        assert reg.get("rule1", "hash1") == "v2"

    def test_different_hashes_are_separate(self):
        reg = ModuleRegistry(feature_flags=_make_flags())
        reg.put("rule1", "hash1", "v1")
        reg.put("rule1", "hash2", "v2")
        assert reg.get("rule1", "hash1") == "v1"
        assert reg.get("rule1", "hash2") == "v2"

    def test_feature_flag_disabled_returns_none(self):
        reg = ModuleRegistry(feature_flags=_make_flags(modular_imports=False))
        reg.put("rule1", "hash1", "value")
        assert reg.get("rule1", "hash1") is None
        assert reg.size == 0


class TestModuleRegistryLRU:
    def test_lru_eviction_at_max_size(self):
        reg = ModuleRegistry(max_size=2, feature_flags=_make_flags())
        reg.put("rule1", "h1", "v1")
        reg.put("rule2", "h1", "v2")
        reg.put("rule3", "h1", "v3")
        assert reg.size == 2
        assert reg.get("rule1", "h1") is None
        assert reg.get("rule2", "h1") == "v2"
        assert reg.get("rule3", "h1") == "v3"

    def test_lru_access_promotes_entry(self):
        reg = ModuleRegistry(max_size=2, feature_flags=_make_flags())
        reg.put("rule1", "h1", "v1")
        reg.put("rule2", "h1", "v2")
        reg.get("rule1", "h1")
        reg.put("rule3", "h1", "v3")
        assert reg.get("rule1", "h1") == "v1"
        assert reg.get("rule2", "h1") is None

    def test_max_size_1(self):
        reg = ModuleRegistry(max_size=1, feature_flags=_make_flags())
        reg.put("rule1", "h1", "v1")
        reg.put("rule2", "h1", "v2")
        assert reg.size == 1
        assert reg.get("rule1", "h1") is None


class TestModuleRegistryTTL:
    def test_expired_entry_returns_none(self):
        reg = ModuleRegistry(ttl_seconds=0.01, feature_flags=_make_flags())
        reg.put("rule1", "h1", "v1")
        time.sleep(0.02)
        assert reg.get("rule1", "h1") is None

    def test_unexpired_entry_returns_value(self):
        reg = ModuleRegistry(ttl_seconds=600, feature_flags=_make_flags())
        reg.put("rule1", "h1", "v1")
        assert reg.get("rule1", "h1") == "v1"


class TestModuleRegistryInvalidation:
    def test_invalidate_by_rule_name(self):
        reg = ModuleRegistry(feature_flags=_make_flags())
        reg.put("rule1", "h1", "v1")
        reg.put("rule1", "h2", "v2")
        reg.put("rule2", "h1", "v3")
        count = reg.invalidate("rule1")
        assert count == 2
        assert reg.get("rule1", "h1") is None
        assert reg.get("rule1", "h2") is None
        assert reg.get("rule2", "h1") == "v3"

    def test_invalidate_transitive_deps(self):
        reg = ModuleRegistry(feature_flags=_make_flags())
        reg.put("lib_a", "h1", "va", dependencies={"lib_core"})
        reg.put("lib_b", "h1", "vb", dependencies={"lib_core"})
        reg.put("lib_c", "h1", "vc", dependencies={"lib_a"})
        count = reg.invalidate("lib_core")
        assert count == 2
        assert reg.get("lib_a", "h1") is None
        assert reg.get("lib_b", "h1") is None
        assert reg.get("lib_c", "h1") == "vc"

    def test_invalidate_nonexistent_rule(self):
        reg = ModuleRegistry(feature_flags=_make_flags())
        assert reg.invalidate("nonexistent") == 0

    def test_invalidate_with_feature_flag_disabled(self):
        reg = ModuleRegistry(feature_flags=_make_flags(modular_imports=False))
        assert reg.invalidate("rule1") == 0


class TestModuleRegistryClear:
    def test_clear_resets_everything(self):
        reg = ModuleRegistry(feature_flags=_make_flags())
        reg.put("rule1", "h1", "v1")
        reg.get("rule1", "h1")
        reg.clear()
        assert reg.size == 0
        assert reg.hit_rate == 0.0


class TestModuleRegistryProperties:
    def test_size(self):
        reg = ModuleRegistry(feature_flags=_make_flags())
        assert reg.size == 0
        reg.put("rule1", "h1", "v1")
        assert reg.size == 1

    def test_hit_rate_no_accesses(self):
        reg = ModuleRegistry(feature_flags=_make_flags())
        assert reg.hit_rate == 0.0

    def test_hit_rate_all_hits(self):
        reg = ModuleRegistry(feature_flags=_make_flags())
        reg.put("rule1", "h1", "v1")
        reg.get("rule1", "h1")
        reg.get("rule1", "h1")
        assert reg.hit_rate == 1.0

    def test_hit_rate_mixed(self):
        reg = ModuleRegistry(feature_flags=_make_flags())
        reg.put("rule1", "h1", "v1")
        reg.get("rule1", "h1")
        reg.get("rule1", "h2")
        assert reg.hit_rate == 0.5

    def test_max_size_property(self):
        reg = ModuleRegistry(max_size=42, feature_flags=_make_flags())
        assert reg.max_size == 42

    def test_ttl_seconds_property(self):
        reg = ModuleRegistry(ttl_seconds=300, feature_flags=_make_flags())
        assert reg.ttl_seconds == 300


class TestModuleRegistryMakeKey:
    def test_make_key(self):
        key = ModuleRegistry.make_key("my_rule", "abc123")
        assert key == "my_rule:abc123"

    def test_compute_content_hash_deterministic(self):
        h1 = ModuleRegistry.compute_content_hash("some content")
        h2 = ModuleRegistry.compute_content_hash("some content")
        assert h1 == h2

    def test_compute_content_hash_different_content(self):
        h1 = ModuleRegistry.compute_content_hash("content a")
        h2 = ModuleRegistry.compute_content_hash("content b")
        assert h1 != h2
