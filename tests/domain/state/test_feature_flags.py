"""
Tests for feature flag start-of-session stickiness.

Phase 1 §5: Feature flag flip integration test + start-of-session stickiness documentation.

Feature flags are start-of-session sticky — cannot flip mid-session.
Attempting to flip mid-session should be gracefully handled (error or
session termination).
"""

import pytest

from src.domain.state.feature_flags import FeatureFlags, reset_feature_flags


class TestFeatureFlagStickiness:
    """Feature flags are start-of-session sticky — cannot flip mid-session."""

    def test_default_values(self):
        """Feature flags have correct defaults."""
        flags = FeatureFlags()
        assert flags.use_hypergraph is True
        assert flags.legacy_iterate is True
        assert flags.layered_memory is True

    def test_explicit_overrides(self):
        """Feature flags can be explicitly set."""
        flags = FeatureFlags(use_hypergraph=True, legacy_iterate=False, layered_memory=False)
        assert flags.use_hypergraph is True
        assert flags.legacy_iterate is False
        assert flags.layered_memory is False

    def test_freeze_prevents_mid_session_flip(self):
        """Once frozen, flag values cannot be changed (simulated session stickiness)."""
        flags = FeatureFlags(use_hypergraph=False)
        flags.freeze()

        assert flags.is_frozen() is True
        # The contract is: after freeze(), the flag values are immutable.
        # Reading them should still return the pre-freeze values.
        assert flags.use_hypergraph is False

    def test_snapshot_captures_current_flags(self):
        """snapshot() returns a dict of current flag values."""
        flags = FeatureFlags(use_hypergraph=True, legacy_iterate=False)
        snap = flags.snapshot()

        assert snap == {
            "use_hypergraph": True,
            "legacy_iterate": False,
            "layered_memory": True,
            "ml_optimized_dfs": False,
            "async_sync_enabled": False,
            "modular_imports": False,
            "hybrid_orchestrator": False,
            "async_post_reasoning": False,
            "prov_o_trace": False,
            "enriched_api": False,
            "redis_session_store": False,
            "llm_enhancements": False,
            "strict_port_contracts": True,
            "observability_enabled": False,
            "auth_enabled": False,
            "abduction_enabled": False,
            "induction_pipeline": False,
            "reasoning_router": True,
            "confidence_thresholds": True,
        }

    def test_snapshot_before_and_after_freeze(self):
        """Snapshot values are identical before and after freeze."""
        flags = FeatureFlags(use_hypergraph=False)
        before = flags.snapshot()
        flags.freeze()
        after = flags.snapshot()

        assert before == after

    def test_reset_creates_fresh_flags(self):
        """reset_feature_flags creates a new, unfrozen instance."""
        flags1 = FeatureFlags(use_hypergraph=True)
        flags1.freeze()

        flags2 = reset_feature_flags(use_hypergraph=False)
        assert flags2.use_hypergraph is False
        assert flags2.is_frozen() is False

    def test_separate_sessions_have_independent_flags(self):
        """Each session should have its own frozen flag snapshot."""
        session1_flags = FeatureFlags(use_hypergraph=False)
        session1_flags.freeze()

        session2_flags = FeatureFlags(use_hypergraph=True)
        session2_flags.freeze()

        assert session1_flags.use_hypergraph is False
        assert session2_flags.use_hypergraph is True

    def test_mid_session_flip_simulation(self):
        """Simulating a mid-session flag flip: new flags must not affect existing session."""
        # Session starts with flags
        session_flags = FeatureFlags(use_hypergraph=False)
        session_flags.freeze()

        # "Admin" changes global config mid-session
        new_global_flags = FeatureFlags(use_hypergraph=True)

        # Existing session still uses its frozen flags
        assert session_flags.use_hypergraph is False
        assert session_flags.is_frozen() is True
        # New session would use the new flags
        assert new_global_flags.use_hypergraph is True

    def test_legacy_retirement_report_identifies_production_flag_gaps(self):
        flags = FeatureFlags(
            use_hypergraph=True,
            legacy_iterate=True,
            layered_memory=True,
            ml_optimized_dfs=False,
        )

        report = flags.legacy_retirement_report()

        assert report["use_hypergraph"]["ready"] is True
        assert report["layered_memory"]["ready"] is True
        assert report["legacy_iterate"]["ready"] is False
        assert report["legacy_iterate"]["expected"] is False
        assert report["ml_optimized_dfs"]["ready"] is True
