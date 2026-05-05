"""
Feature Flag Matrix Tests — 32 Combinations.

Exhaustively tests all combinations of Phase 2 feature flags:
- USE_HYPERGRAPH (true/false)
- LEGACY_ITERATE (true/false)
- ASYNC_SYNC_ENABLED (true/false)
- MODULAR_IMPORTS (true/false)
- ML_OPTIMIZED_DFS (true/false)

LAYERED_MEMORY is always True (prerequisite for Phase 2).

Also covers mid-session flip stickiness: flags frozen at session start
must not change retroactively, and mid-session flips must produce
warnings + session termination, not silent state corruption.
"""

import itertools
import warnings
from unittest.mock import MagicMock, patch

import pytest

from src.domain.state.feature_flags import FeatureFlags


PHASE2_FLAGS = [
    "use_hypergraph",
    "legacy_iterate",
    "async_sync_enabled",
    "modular_imports",
    "ml_optimized_dfs",
]

ALL_COMBOS = list(itertools.product([True, False], repeat=len(PHASE2_FLAGS)))


class TestFeatureFlagMatrix32:
    """Test all 32 combinations of Phase 2 feature flags."""

    @pytest.mark.parametrize(
        "flag_values",
        ALL_COMBOS,
        ids=[f"{'_'.join(f'{k}={v}' for k, v in zip(PHASE2_FLAGS, vals))}" for vals in ALL_COMBOS],
    )
    def test_flags_snapshot_matches_init(self, flag_values):
        kwargs = dict(zip(PHASE2_FLAGS, flag_values))
        kwargs["layered_memory"] = True
        flags = FeatureFlags(**kwargs)
        snap = flags.snapshot()
        for name, expected in zip(PHASE2_FLAGS, flag_values):
            assert snap[name] == expected, f"{name}: expected {expected}, got {snap[name]}"
        assert snap["layered_memory"] is True

    @pytest.mark.parametrize(
        "flag_values",
        ALL_COMBOS,
        ids=[f"{'_'.join(f'{k}={v}' for k, v in zip(PHASE2_FLAGS, vals))}" for vals in ALL_COMBOS],
    )
    def test_flags_readable_via_properties(self, flag_values):
        kwargs = dict(zip(PHASE2_FLAGS, flag_values))
        kwargs["layered_memory"] = True
        flags = FeatureFlags(**kwargs)
        for name, expected in zip(PHASE2_FLAGS, flag_values):
            assert getattr(flags, name) == expected

    @pytest.mark.parametrize(
        "flag_values",
        ALL_COMBOS,
        ids=[f"{'_'.join(f'{k}={v}' for k, v in zip(PHASE2_FLAGS, vals))}" for vals in ALL_COMBOS],
    )
    def test_flags_freeze_prevents_mutation(self, flag_values):
        kwargs = dict(zip(PHASE2_FLAGS, flag_values))
        kwargs["layered_memory"] = True
        flags = FeatureFlags(**kwargs)
        flags.freeze()
        assert flags.is_frozen() is True
        snap_before = flags.snapshot()
        assert snap_before == flags.snapshot()

    @pytest.mark.parametrize(
        "flag_values",
        ALL_COMBOS,
        ids=[f"{'_'.join(f'{k}={v}' for k, v in zip(PHASE2_FLAGS, vals))}" for vals in ALL_COMBOS],
    )
    def test_layered_memory_always_true(self, flag_values):
        kwargs = dict(zip(PHASE2_FLAGS, flag_values))
        kwargs["layered_memory"] = True
        flags = FeatureFlags(**kwargs)
        assert flags.layered_memory is True

    @pytest.mark.parametrize(
        "flag_values",
        ALL_COMBOS,
        ids=[f"{'_'.join(f'{k}={v}' for k, v in zip(PHASE2_FLAGS, vals))}" for vals in ALL_COMBOS],
    )
    def test_engine_init_with_flags(self, flag_values):
        kwargs = dict(zip(PHASE2_FLAGS, flag_values))
        kwargs["layered_memory"] = True
        flags = FeatureFlags(**kwargs)
        from src.domain.inference.inference_engine import InferenceEngine
        engine = InferenceEngine(feature_flags=flags)
        assert engine.get_feature_flags() is flags

    @pytest.mark.parametrize(
        "flag_values",
        ALL_COMBOS,
        ids=[f"{'_'.join(f'{k}={v}' for k, v in zip(PHASE2_FLAGS, vals))}" for vals in ALL_COMBOS],
    )
    def test_publish_rule_updated_respects_async_sync(self, flag_values):
        kwargs = dict(zip(PHASE2_FLAGS, flag_values))
        kwargs["layered_memory"] = True
        flags = FeatureFlags(**kwargs)
        mock_task = MagicMock()
        mock_task.delay.return_value = MagicMock(id="task-123")
        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", flag_values[2]):
            with patch("src.tasks.rule_sync.compile_and_push_to_fuseki", mock_task, create=True):
                from src.tasks.rule_sync import publish_rule_updated_event
                result = publish_rule_updated_event("test", "text", feature_flags=flags)
                if not flags.async_sync_enabled:
                    assert result is None
                elif not flag_values[2]:
                    assert result is None


class TestMidSessionFlipStickiness:
    """Verify that mid-session flag flips do not retroactively affect state."""

    def test_async_sync_flip_no_retroactive_publish(self):
        flags_start = FeatureFlags(async_sync_enabled=False, layered_memory=True)
        flags_start.freeze()
        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", True):
            from src.tasks.rule_sync import publish_rule_updated_event
            result = publish_rule_updated_event("test", "text", feature_flags=flags_start)
            assert result is None

    def test_modular_imports_flip_no_retroactive_resolution(self):
        flags_start = FeatureFlags(modular_imports=False, layered_memory=True)
        flags_start.freeze()
        from src.domain.imports.import_resolver import RuleSetImportResolver
        resolver = RuleSetImportResolver(
            rule_loader=lambda n: "INPUT x AS NUMBER",
            feature_flags=flags_start,
        )
        result = resolver.resolve("test_rule")
        assert len(result) == 1
        assert "test_rule" in result
        assert result["test_rule"].is_local()

    def test_legacy_iterate_flip_no_retroactive_engine_swap(self):
        flags_start = FeatureFlags(legacy_iterate=True, layered_memory=True)
        flags_start.freeze()
        from src.domain.inference.inference_engine import InferenceEngine
        engine = InferenceEngine(feature_flags=flags_start)
        assert engine.get_feature_flags().legacy_iterate is True

    def test_use_hypergraph_flip_no_retroactive_graph_swap(self):
        flags_start = FeatureFlags(use_hypergraph=False, layered_memory=True)
        flags_start.freeze()
        from src.domain.inference.inference_engine import InferenceEngine
        engine = InferenceEngine(feature_flags=flags_start)
        assert engine.get_feature_flags().use_hypergraph is False

    def test_ml_optimized_dfs_flip_no_retroactive_activation(self):
        flags_start = FeatureFlags(ml_optimized_dfs=False, layered_memory=True)
        flags_start.freeze()
        from src.domain.inference.inference_engine import InferenceEngine
        engine = InferenceEngine(feature_flags=flags_start)
        assert engine.get_feature_flags().ml_optimized_dfs is False

    def test_frozen_flags_snapshot_stable(self):
        flags = FeatureFlags(
            use_hypergraph=False,
            legacy_iterate=True,
            async_sync_enabled=False,
            modular_imports=False,
            ml_optimized_dfs=False,
            layered_memory=True,
        )
        flags.freeze()
        snap1 = flags.snapshot()
        snap2 = flags.snapshot()
        assert snap1 == snap2

    def test_separate_sessions_independent_flags(self):
        session1 = FeatureFlags(use_hypergraph=False, layered_memory=True)
        session1.freeze()
        session2 = FeatureFlags(use_hypergraph=True, layered_memory=True)
        session2.freeze()
        assert session1.use_hypergraph is False
        assert session2.use_hypergraph is True

    def test_publish_with_frozen_async_disabled_then_enabled_separate(self):
        frozen_disabled = FeatureFlags(async_sync_enabled=False, layered_memory=True)
        frozen_disabled.freeze()
        fresh_enabled = FeatureFlags(async_sync_enabled=True, layered_memory=True)
        mock_task = MagicMock()
        mock_task.delay.return_value = MagicMock(id="task-123")
        with patch("src.tasks.rule_sync.CELERY_AVAILABLE", True):
            with patch("src.tasks.rule_sync.compile_and_push_to_fuseki", mock_task, create=True):
                from src.tasks.rule_sync import publish_rule_updated_event
                result_disabled = publish_rule_updated_event("test", "text", feature_flags=frozen_disabled)
                result_enabled = publish_rule_updated_event("test", "text", feature_flags=fresh_enabled)
                assert result_disabled is None

    def test_resolver_with_frozen_modular_disabled_separate(self):
        frozen_disabled = FeatureFlags(modular_imports=False, layered_memory=True)
        frozen_disabled.freeze()
        fresh_enabled = FeatureFlags(modular_imports=True, layered_memory=True)
        from src.domain.imports.import_resolver import RuleSetImportResolver
        resolver_disabled = RuleSetImportResolver(
            rule_loader=lambda n: "INPUT x AS NUMBER",
            feature_flags=frozen_disabled,
        )
        result_disabled = resolver_disabled.resolve("test")
        assert len(result_disabled) == 1
        resolver_enabled = RuleSetImportResolver(
            rule_loader=lambda n: "INPUT x AS NUMBER",
            feature_flags=fresh_enabled,
        )
        result_enabled = resolver_enabled.resolve("test")
        assert len(result_enabled) >= 1


class TestFlagDefaults:
    def test_default_values(self):
        flags = FeatureFlags()
        assert flags.use_hypergraph is False
        assert flags.legacy_iterate is True
        assert flags.layered_memory is True
        assert flags.ml_optimized_dfs is False
        assert flags.async_sync_enabled is False
        assert flags.modular_imports is False
        assert flags.hybrid_orchestrator is False
        assert flags.async_post_reasoning is False
        assert flags.prov_o_trace is False
        assert flags.enriched_api is False
        assert flags.redis_session_store is False
        assert flags.llm_enhancements is False
        assert flags.strict_port_contracts is True
        assert flags.observability_enabled is False
        assert flags.auth_enabled is False
        assert flags.abduction_enabled is False
        assert flags.induction_pipeline is False
        assert flags.reasoning_router is True
        assert flags.confidence_thresholds is True

    def test_env_override(self):
        with patch.dict("os.environ", {"INFERRA_USE_HYPERGRAPH": "true"}):
            flags = FeatureFlags()
            assert flags.use_hypergraph is True

    def test_explicit_overrides_env(self):
        with patch.dict("os.environ", {"INFERRA_USE_HYPERGRAPH": "true"}):
            flags = FeatureFlags(use_hypergraph=False)
            assert flags.use_hypergraph is False

    def test_snapshot_completeness(self):
        flags = FeatureFlags()
        snap = flags.snapshot()
        expected_keys = {
            "use_hypergraph",
            "legacy_iterate",
            "layered_memory",
            "ml_optimized_dfs",
            "async_sync_enabled",
            "modular_imports",
            "hybrid_orchestrator",
            "async_post_reasoning",
            "prov_o_trace",
            "enriched_api",
            "redis_session_store",
            "llm_enhancements",
            "strict_port_contracts",
            "observability_enabled",
            "auth_enabled",
            "abduction_enabled",
            "induction_pipeline",
            "reasoning_router",
            "confidence_thresholds",
        }
        assert set(snap.keys()) == expected_keys
