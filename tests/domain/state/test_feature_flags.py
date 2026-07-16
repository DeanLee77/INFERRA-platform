"""
Tests for feature flag start-of-session stickiness.

Phase 1 §5: Feature flag flip integration test + start-of-session stickiness documentation.

Feature flags are start-of-session sticky — cannot flip mid-session.
Attempting to flip mid-session should be gracefully handled (error or
session termination).
"""

import pytest

import src.domain.state.feature_flags as feature_flags_module
from src.domain.state.feature_flags import (
    FeatureFlagSnapshotMismatchError,
    FeatureFlags,
    assert_feature_flag_snapshot_match,
    build_effective_feature_flag_report,
    canonical_feature_flag_defaults,
    feature_flag_snapshot_hash,
    feature_flags_from_snapshot,
    get_feature_flags,
    get_feature_flag_specs,
    normalize_ontology_flag_overrides,
    normalize_ontology_profile,
    reset_feature_flags,
    validate_runtime_feature_flags,
)


class TestFeatureFlagStickiness:
    """Feature flags are start-of-session sticky — cannot flip mid-session."""

    def test_default_values(self):
        """Feature flags have correct defaults."""
        flags = FeatureFlags()
        assert flags.snapshot() == canonical_feature_flag_defaults()

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

        expected = canonical_feature_flag_defaults()
        expected.update(use_hypergraph=True, legacy_iterate=False)

        assert snap == expected
        assert tuple(snap) == tuple(spec.key for spec in get_feature_flag_specs())
        assert len(snap) == 28

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

    def test_process_flags_are_built_lazily_and_remain_stable(self, monkeypatch):
        monkeypatch.setattr(feature_flags_module, "_default_flags", None)
        monkeypatch.setenv("INFERRA_USE_HYPERGRAPH", "false")

        first = get_feature_flags()
        monkeypatch.setenv("INFERRA_USE_HYPERGRAPH", "true")
        second = get_feature_flags()

        assert first is second
        assert second.use_hypergraph is False

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
        assert report["strict_port_contracts"]["ready"] is True
        assert report["strict_port_contracts"]["status"] == "retirement_pending"

    def test_ontology_advisory_flag_defaults_disabled(self):
        flags = FeatureFlags()
        assert flags.ontology_advisory_enabled is False

    def test_ontology_advisory_flag_can_be_enabled(self):
        flags = FeatureFlags(ontology_advisory_enabled=True)
        assert flags.ontology_advisory_enabled is True

    def test_ontology_auto_answer_defaults_disabled(self):
        flags = FeatureFlags()
        assert flags.ontology_auto_answer is False
        assert flags.ontology_auto_answer_confidence_threshold == 0.85

    def test_ontology_auto_answer_can_be_enabled(self):
        flags = FeatureFlags(
            ontology_auto_answer=True,
            ontology_auto_answer_confidence_threshold=0.95,
        )
        assert flags.ontology_auto_answer is True
        assert flags.ontology_auto_answer_confidence_threshold == 0.95

    def test_ontology_reasoning_defaults_disabled(self):
        flags = FeatureFlags()
        assert flags.ontology_reasoning is False
        assert flags.ontology_reasoning_confidence_threshold == 0.85
        assert flags.ontology_reasoning_min_hierarchy_depth == 1
        assert flags.ontology_reasoning_max_closure_depth == 10
        assert flags.ontology_question_strategy is False

    def test_ontology_reasoning_can_be_enabled(self):
        flags = FeatureFlags(
            ontology_reasoning=True,
            ontology_reasoning_confidence_threshold=0.9,
            ontology_reasoning_min_hierarchy_depth=2,
            ontology_reasoning_max_closure_depth=8,
            ontology_question_strategy=True,
        )
        assert flags.ontology_reasoning is True
        assert flags.ontology_reasoning_confidence_threshold == 0.9
        assert flags.ontology_reasoning_min_hierarchy_depth == 2
        assert flags.ontology_reasoning_max_closure_depth == 8
        assert flags.ontology_question_strategy is True

    def test_ontology_profile_reasoning_maps_to_expected_flags(self):
        flags, profile = feature_flags_from_snapshot(
            FeatureFlags().snapshot(),
            ontology_profile="reasoning",
        )

        assert profile == "reasoning"
        assert flags.ontology_advisory_enabled is True
        assert flags.ontology_auto_answer is True
        assert flags.ontology_reasoning is True
        assert flags.ontology_question_strategy is False

    def test_ontology_profile_full_semantic_pilot_enables_all_ontology_modes(self):
        flags, profile = feature_flags_from_snapshot(
            FeatureFlags().snapshot(),
            ontology_profile="full-semantic-pilot",
        )

        assert profile == "full_semantic_pilot"
        assert flags.ontology_advisory_enabled is True
        assert flags.ontology_auto_answer is True
        assert flags.ontology_reasoning is True
        assert flags.ontology_question_strategy is True

    def test_invalid_ontology_profile_is_rejected(self):
        with pytest.raises(ValueError, match="Unsupported ontology_profile"):
            normalize_ontology_profile("surprise_mode")

    def test_ontology_flag_overrides_can_create_custom_case_policy(self):
        flags, profile = feature_flags_from_snapshot(
            FeatureFlags().snapshot(),
            ontology_profile="reasoning",
            ontology_flags={"auto_answer_enabled": False},
        )

        assert profile == "custom"
        assert flags.ontology_advisory_enabled is True
        assert flags.ontology_auto_answer is False
        assert flags.ontology_reasoning is True
        assert flags.ontology_question_strategy is False

    def test_invalid_ontology_flag_override_is_rejected(self):
        with pytest.raises(ValueError, match="Unsupported ontology flag override"):
            normalize_ontology_flag_overrides({"surprise": True})

    def test_question_strategy_enabled_env_name_is_supported(self, monkeypatch):
        monkeypatch.setenv("INFERRA_ONTOLOGY_QUESTION_STRATEGY_ENABLED", "true")

        flags = FeatureFlags()

        assert flags.ontology_question_strategy is True


@pytest.mark.parametrize(
    "key",
    ["use_hypergraph", "layered_memory", "strict_port_contracts"],
)
def test_runtime_invariants_reject_required_flag_disabled(key):
    values = canonical_feature_flag_defaults()
    values[key] = False

    with pytest.raises(RuntimeError, match=rf"{key} must be true"):
        validate_runtime_feature_flags(FeatureFlags(**values))


@pytest.mark.parametrize(
    ("async_enabled", "ttl_enabled"),
    [(True, False), (False, True)],
)
def test_runtime_invariants_reject_half_enabled_post_reasoning(
    async_enabled,
    ttl_enabled,
):
    flags = FeatureFlags(
        async_post_reasoning=async_enabled,
        generate_post_reasoning_ttl=ttl_enabled,
    )

    with pytest.raises(RuntimeError, match="must be enabled or disabled together"):
        validate_runtime_feature_flags(flags)


def test_runtime_invariants_accept_canonical_defaults_and_return_same_instance():
    flags = FeatureFlags()

    assert validate_runtime_feature_flags(flags) is flags


def test_snapshot_hash_is_stable_and_requires_canonical_shape():
    defaults = canonical_feature_flag_defaults()
    reversed_snapshot = dict(reversed(tuple(defaults.items())))

    assert feature_flag_snapshot_hash(defaults) == feature_flag_snapshot_hash(
        reversed_snapshot
    )
    assert len(feature_flag_snapshot_hash(defaults)) == 64

    incomplete = dict(defaults)
    incomplete.pop("reasoning_router")
    with pytest.raises(ValueError, match="missing: reasoning_router"):
        feature_flag_snapshot_hash(incomplete)


def test_effective_report_contains_defaults_values_sources_and_retirement(monkeypatch):
    monkeypatch.setenv("INFERRA_REASONING_ROUTER", "false")
    flags = FeatureFlags()

    report = build_effective_feature_flag_report(
        "API",
        flags=flags,
        deployment_profile="Production",
    )

    assert report["process_role"] == "api"
    assert report["deployment_profile"] == "production"
    assert report["flag_count"] == 28
    assert report["canonical_defaults"]["reasoning_router"] is True
    assert report["effective"]["reasoning_router"] is False
    assert report["sources"]["reasoning_router"] == {
        "classification": "environment",
        "environment_name": "INFERRA_REASONING_ROUTER",
    }
    assert report["legacy_retirement"]["strict_port_contracts"]["ready"] is True
    assert report["snapshot_hash"] == feature_flag_snapshot_hash(flags.snapshot())


def test_cross_process_snapshot_mismatch_is_rejected():
    publisher_hash = feature_flag_snapshot_hash(FeatureFlags().snapshot())
    worker_flags = FeatureFlags(reasoning_router=False)

    with pytest.raises(
        FeatureFlagSnapshotMismatchError,
        match="publisher=.*worker=",
    ):
        assert_feature_flag_snapshot_match(
            publisher_hash,
            flags=worker_flags,
        )

    assert assert_feature_flag_snapshot_match(None, flags=worker_flags) == (
        feature_flag_snapshot_hash(worker_flags.snapshot())
    )
