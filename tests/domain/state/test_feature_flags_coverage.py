"""Focused branch coverage for the canonical feature-flag registry."""

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from src.domain.state import feature_flags as feature_flags_module
from src.domain.state.feature_flags import (
    FeatureFlags,
    build_effective_feature_flag_report,
    canonical_feature_flag_defaults,
    feature_flag_snapshot_hash,
    feature_flag_value_sources,
)


@pytest.mark.parametrize(
    ("source_fragment", "replacement", "message"),
    [
        (
            "EXPECTED_FEATURE_FLAG_COUNT = 28",
            "EXPECTED_FEATURE_FLAG_COUNT = 27",
            "Expected 27 canonical feature flag entries",
        ),
        (
            'key="legacy_iterate"',
            'key="use_hypergraph"',
            "snapshot keys must be unique",
        ),
        (
            'minimum_from_key="ontology_reasoning_min_hierarchy_depth"',
            'minimum_from_key="unknown_constraint_source"',
            "numeric constraint references an unknown key",
        ),
        (
            'env_name="INFERRA_LEGACY_ITERATE"',
            'env_name="INFERRA_USE_HYPERGRAPH"',
            "environment names must be unique",
        ),
        (
            'aliases=("INFERRA_ONTOLOGY_QUESTION_STRATEGY",)',
            'aliases=("INFERRA_USE_HYPERGRAPH",)',
            "environment names and aliases must be unique",
        ),
    ],
)
def test_import_time_registry_invariants_reject_invalid_metadata(
    monkeypatch,
    source_fragment: str,
    replacement: str,
    message: str,
) -> None:
    source_path = Path(feature_flags_module.__file__)
    source = source_path.read_text(encoding="utf-8")
    assert source_fragment in source
    invalid_source = source.replace(source_fragment, replacement, 1)
    module_name = f"_invalid_feature_flags_{abs(hash(replacement))}"
    isolated_module = ModuleType(module_name)
    isolated_module.__file__ = str(source_path)
    isolated_module.__package__ = "src.domain.state"
    monkeypatch.setitem(sys.modules, module_name, isolated_module)

    with pytest.raises(RuntimeError, match=message):
        exec(
            compile(invalid_source, str(source_path), "exec"),
            isolated_module.__dict__,
        )


def test_unsupported_runtime_value_types_are_rejected() -> None:
    unsupported = SimpleNamespace(key="custom_flag", value_type=str)

    with pytest.raises(TypeError, match="Unsupported feature flag type"):
        FeatureFlags._value_from_environment(unsupported)
    with pytest.raises(TypeError, match="Unsupported feature flag type"):
        FeatureFlags._validated_value(unsupported, "enabled")


def test_snapshot_hash_rejects_unexpected_keys() -> None:
    snapshot = canonical_feature_flag_defaults()
    snapshot["unexpected_flag"] = True

    with pytest.raises(ValueError, match="unexpected: unexpected_flag"):
        feature_flag_snapshot_hash(snapshot)


def test_value_sources_identify_explicit_constructor_overrides() -> None:
    flags = FeatureFlags(async_sync_enabled=True)

    sources = feature_flag_value_sources(flags, environment={})

    assert sources["async_sync_enabled"] == {
        "classification": "explicit_override",
        "environment_name": None,
    }


def test_effective_report_rejects_empty_roles_and_normalizes_blank_profiles() -> None:
    with pytest.raises(ValueError, match="process_role must not be empty"):
        build_effective_feature_flag_report("   ")

    report = build_effective_feature_flag_report(
        "worker",
        flags=FeatureFlags(),
        deployment_profile="   ",
        environment={},
    )

    assert report["deployment_profile"] == "unspecified"
