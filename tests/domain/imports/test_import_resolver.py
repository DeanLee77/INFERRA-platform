"""
Tests for RuleSetImportResolver — DFS cycle detection, depth guard, timeout,
feature flag gating, and resolution.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.domain.imports.import_resolver import (
    MAX_IMPORT_DEPTH,
    CircularImportError,
    ImportDepthExceededError,
    RuleLoadTimeoutError,
    RuleSetImportResolver,
)
from src.domain.imports.node_origin import NodeOrigin
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


class TestRuleSetImportResolverBasic:
    def test_resolve_no_imports(self):
        loader = MagicMock(return_value="RULE\n  AND child")
        resolver = RuleSetImportResolver(rule_loader=loader, feature_flags=_make_flags())
        result = resolver.resolve("main_rule")
        assert "main_rule" in result
        assert result["main_rule"].is_local()

    def test_resolve_single_import(self):
        def loader(name):
            if name == "main":
                return "IMPORT: lib_a\nRULE\n  AND child"
            if name == "lib_a":
                return "RULE\n  AND lib_child"
            raise FileNotFoundError(name)

        resolver = RuleSetImportResolver(rule_loader=loader, feature_flags=_make_flags())
        result = resolver.resolve("main")
        assert "main" in result
        assert "lib_a" in result
        assert result["lib_a"].imported is True
        assert result["lib_a"].depth == 1

    def test_resolve_transitive_imports(self):
        def loader(name):
            texts = {
                "root": "IMPORT: mid\nRULE",
                "mid": "IMPORT: leaf\nRULE2",
                "leaf": "RULE3",
            }
            return texts[name]

        resolver = RuleSetImportResolver(rule_loader=loader, feature_flags=_make_flags())
        result = resolver.resolve("root")
        assert "root" in result
        assert "mid" in result
        assert "leaf" in result
        assert result["mid"].depth == 1
        assert result["leaf"].depth == 2

    def test_resolve_diamond_import(self):
        """Two modules import the same leaf — leaf should appear once."""
        def loader(name):
            texts = {
                "root": "IMPORT: left\nIMPORT: right\nRULE",
                "left": "IMPORT: shared\nLEFT",
                "right": "IMPORT: shared\nRIGHT",
                "shared": "SHARED",
            }
            return texts[name]

        resolver = RuleSetImportResolver(rule_loader=loader, feature_flags=_make_flags())
        result = resolver.resolve("root")
        assert "shared" in result
        assert result["shared"].imported is True

    def test_feature_flag_disabled_returns_root_only(self):
        loader = MagicMock(return_value="IMPORT: lib_a\nRULE")
        flags = _make_flags(modular_imports=False)
        resolver = RuleSetImportResolver(rule_loader=loader, feature_flags=flags)
        result = resolver.resolve("main")
        assert list(result.keys()) == ["main"]
        assert result["main"].is_local()
        loader.assert_not_called()


class TestCircularImportDetection:
    def test_direct_circular_import(self):
        def loader(name):
            texts = {
                "a": "IMPORT: b\nRULE_A",
                "b": "IMPORT: a\nRULE_B",
            }
            return texts[name]

        resolver = RuleSetImportResolver(rule_loader=loader, feature_flags=_make_flags())
        with pytest.raises(CircularImportError) as exc_info:
            resolver.resolve("a")
        assert "a" in exc_info.value.import_chain
        assert "b" in exc_info.value.import_chain

    def test_indirect_circular_import(self):
        def loader(name):
            texts = {
                "a": "IMPORT: b\nRULE_A",
                "b": "IMPORT: c\nRULE_B",
                "c": "IMPORT: a\nRULE_C",
            }
            return texts[name]

        resolver = RuleSetImportResolver(rule_loader=loader, feature_flags=_make_flags())
        with pytest.raises(CircularImportError):
            resolver.resolve("a")

    def test_self_import(self):
        def loader(name):
            return "IMPORT: self_ref\nRULE"

        resolver = RuleSetImportResolver(rule_loader=loader, feature_flags=_make_flags())
        with pytest.raises(CircularImportError):
            resolver.resolve("self_ref")


class TestImportDepthGuard:
    def test_depth_exceeded_raises_error(self):
        call_count = 0

        def loader(name):
            nonlocal call_count
            call_count += 1
            return f"IMPORT: deep_{call_count}\nRULE"

        resolver = RuleSetImportResolver(rule_loader=loader, feature_flags=_make_flags())
        with pytest.raises(ImportDepthExceededError) as exc_info:
            resolver.resolve("deep_0")
        assert exc_info.value.depth > MAX_IMPORT_DEPTH

    def test_max_depth_constant(self):
        assert MAX_IMPORT_DEPTH == 100


class TestRuleLoadTimeout:
    def test_slow_loader_raises_timeout(self):
        def slow_loader(name):
            time.sleep(5)
            return "RULE"

        resolver = RuleSetImportResolver(
            rule_loader=slow_loader,
            feature_flags=_make_flags(),
            load_timeout_s=0.1,
        )
        with pytest.raises(RuleLoadTimeoutError):
            resolver.resolve("slow_rule")

    def test_fast_loader_succeeds(self):
        def fast_loader(name):
            return "RULE"

        resolver = RuleSetImportResolver(
            rule_loader=fast_loader,
            feature_flags=_make_flags(),
            load_timeout_s=10,
        )
        result = resolver.resolve("fast_rule")
        assert "fast_rule" in result

    def test_loader_exception_propagates(self):
        def failing_loader(name):
            raise FileNotFoundError(f"Rule '{name}' not found")

        resolver = RuleSetImportResolver(
            rule_loader=failing_loader,
            feature_flags=_make_flags(),
        )
        result = resolver.resolve("missing")
        assert "missing" in result
        assert result["missing"].is_local()


class TestGetImportChain:
    def test_returns_direct_imports(self):
        def loader(name):
            if name == "main":
                return "IMPORT: a\nIMPORT: b\nRULE"
            return "RULE"

        resolver = RuleSetImportResolver(rule_loader=loader, feature_flags=_make_flags())
        chain = resolver.get_import_chain("main")
        assert chain == ["a", "b"]

    def test_returns_empty_for_no_imports(self):
        loader = MagicMock(return_value="RULE\n  AND child")
        resolver = RuleSetImportResolver(rule_loader=loader, feature_flags=_make_flags())
        assert resolver.get_import_chain("rule1") == []

    def test_returns_empty_on_load_failure(self):
        def failing_loader(name):
            raise FileNotFoundError(name)

        resolver = RuleSetImportResolver(
            rule_loader=failing_loader, feature_flags=_make_flags()
        )
        assert resolver.get_import_chain("missing") == []


class TestCircularImportError:
    def test_chain_in_message(self):
        err = CircularImportError(["a", "b", "a"])
        assert "a" in str(err)
        assert "→" in str(err)

    def test_import_chain_attribute(self):
        err = CircularImportError(["x", "y", "x"])
        assert err.import_chain == ["x", "y", "x"]


class TestImportDepthExceededError:
    def test_attributes(self):
        err = ImportDepthExceededError(depth=101, module_name="deep_mod")
        assert err.depth == 101
        assert err.module_name == "deep_mod"
        assert "101" in str(err)
        assert "deep_mod" in str(err)


class TestRuleLoadTimeoutError:
    def test_attributes(self):
        err = RuleLoadTimeoutError(module_name="slow", timeout_s=10.0)
        assert err.module_name == "slow"
        assert err.timeout_s == 10.0
        assert "10.0" in str(err)
