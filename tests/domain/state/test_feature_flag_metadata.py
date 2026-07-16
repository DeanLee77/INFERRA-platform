"""Canonical feature-flag metadata and drift checks."""

import inspect
import re
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

import src.domain.state.feature_flags as feature_flags_module
import src.infrastructure.auth_middleware as auth_middleware
from src.domain.reasoning.ontology_reasoner import OntologyReasoner
from src.domain.reasoning.reasoning_router import ReasoningRouter
from src.domain.session.inference_context import InferenceContext
from src.domain.state.feature_flags import (
    EXPECTED_FEATURE_FLAG_COUNT,
    FeatureFlagSpec,
    FeatureFlags,
    canonical_feature_flag_defaults,
    get_effective_feature_flag_snapshot,
    get_feature_flag_default,
    get_feature_flag_spec,
    get_feature_flag_specs,
    normalize_ontology_profile,
    ontology_flags_snapshot,
)


ROOT = Path(__file__).resolve().parents[3]

APPROVED_BOOLEAN_CONSUMERS = {
    "use_hypergraph": (
        "src/domain/state/feature_flags.py",
        '"use_hypergraph": "HyperAdjacencyGraph',
    ),
    "legacy_iterate": (
        "src/domain/nodes/iterate_line.py",
        ".legacy_iterate",
    ),
    "layered_memory": (
        "src/domain/state/feature_flags.py",
        '"layered_memory": "Phase 2+ truth maintenance',
    ),
    "ml_optimized_dfs": (
        "src/domain/inference/session_service.py",
        ".ml_optimized_dfs",
    ),
    "async_sync_enabled": ("src/tasks/rule_sync.py", ".async_sync_enabled"),
    "modular_imports": (
        "src/domain/imports/import_resolver.py",
        ".modular_imports",
    ),
    "hybrid_orchestrator": (
        "src/infrastructure/orchestrator_factory.py",
        ".hybrid_orchestrator",
    ),
    "async_post_reasoning": (
        "src/tasks/ontology_post_reasoner.py",
        ".async_post_reasoning",
    ),
    "generate_post_reasoning_ttl": (
        "src/tasks/ontology_post_reasoner.py",
        ".generate_post_reasoning_ttl",
    ),
    "prov_o_trace": (
        "src/adapters/inbound/http/routes/inference.py",
        ".prov_o_trace",
    ),
    "enriched_api": (
        "src/adapters/inbound/http/routes/inference.py",
        ".enriched_api",
    ),
    "ontology_advisory_enabled": (
        "src/domain/inference/session_service.py",
        ".ontology_advisory_enabled",
    ),
    "ontology_auto_answer": (
        "src/domain/inference/inference_engine.py",
        ".ontology_auto_answer",
    ),
    "ontology_reasoning": (
        "src/domain/inference/session_service.py",
        ".ontology_reasoning",
    ),
    "ontology_question_strategy": (
        "src/domain/inference/session_service.py",
        ".ontology_question_strategy",
    ),
    "redis_session_store": (
        "src/adapters/inbound/http/dependencies.py",
        ".redis_session_store",
    ),
    "llm_enhancements": (
        "src/adapters/outbound/llm/factory.py",
        ".llm_enhancements",
    ),
    "strict_port_contracts": (
        "src/domain/state/feature_flags.py",
        '"strict_port_contracts": "port contracts',
    ),
    "observability_enabled": (
        "src/infrastructure/observability.py",
        ".observability_enabled",
    ),
    "auth_enabled": (
        "src/infrastructure/auth_middleware.py",
        ".auth_enabled",
    ),
    "abduction_enabled": (
        "src/adapters/outbound/reasoning/factory.py",
        ".abduction_enabled",
    ),
    "induction_pipeline": (
        "src/adapters/outbound/reasoning/factory.py",
        ".induction_pipeline",
    ),
    "reasoning_router": (
        "src/adapters/outbound/reasoning/factory.py",
        ".reasoning_router",
    ),
    "confidence_thresholds": (
        "src/adapters/outbound/reasoning/factory.py",
        ".confidence_thresholds",
    ),
}


def _default_text(value) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _clear_feature_flag_environment(monkeypatch) -> None:
    for spec in get_feature_flag_specs():
        for env_name in spec.environment_names:
            monkeypatch.delenv(env_name, raising=False)


def _environment_sample(spec):
    if spec.value_type is bool:
        expected = not spec.default
        return _default_text(expected), expected
    if spec.value_type is float:
        return "0.42", 0.42
    return "3", 3


def test_canonical_metadata_is_complete_unique_and_immutable():
    specs = get_feature_flag_specs()

    assert isinstance(specs, tuple)
    assert len(specs) == EXPECTED_FEATURE_FLAG_COUNT == 28
    assert sum(spec.value_type is bool for spec in specs) == 24
    assert sum(spec.value_type in (float, int) for spec in specs) == 4
    assert len({spec.key for spec in specs}) == len(specs)
    assert len({spec.env_name for spec in specs}) == len(specs)
    assert all(spec.session_sticky for spec in specs)
    assert {
        alias
        for spec in specs
        for alias in spec.aliases
    } == {"INFERRA_ONTOLOGY_QUESTION_STRATEGY"}

    with pytest.raises(FrozenInstanceError):
        specs[0].default = False


def test_every_boolean_flag_has_an_approved_production_consumer():
    boolean_keys = {
        spec.key
        for spec in get_feature_flag_specs()
        if spec.value_type is bool
    }

    assert set(APPROVED_BOOLEAN_CONSUMERS) == boolean_keys
    for key, (relative_path, token) in APPROVED_BOOLEAN_CONSUMERS.items():
        source_path = ROOT / relative_path
        assert source_path.is_file(), f"Missing consumer module for {key}: {relative_path}"
        assert token in source_path.read_text(encoding="utf-8"), (
            f"Approved consumer for {key} no longer contains {token!r}"
        )


@pytest.mark.parametrize(
    ("replacement", "error"),
    (
        ({"key": "USE_HYPERGRAPH"}, ValueError),
        ({"env_name": "USE_HYPERGRAPH"}, ValueError),
        ({"value_type": str, "default": "true"}, TypeError),
        ({"value_type": int}, TypeError),
        ({"phase": 6}, ValueError),
        ({"description": " "}, ValueError),
        ({"minimum": 0}, TypeError),
        (
            {
                "value_type": int,
                "default": 1,
                "minimum": 2,
                "maximum": 1,
            },
            ValueError,
        ),
        ({"minimum_from_key": ""}, ValueError),
        ({"aliases": ("ONTOLOGY_QUESTION_STRATEGY",)}, ValueError),
    ),
)
def test_metadata_rejects_invalid_definitions(replacement, error):
    values = {
        "key": "use_hypergraph",
        "env_name": "INFERRA_USE_HYPERGRAPH",
        "value_type": bool,
        "default": True,
        "phase": 1,
        "description": "Use the canonical graph.",
    }
    values.update(replacement)

    with pytest.raises(error):
        FeatureFlagSpec(**values)


def test_unknown_metadata_key_has_a_clear_error():
    with pytest.raises(KeyError, match="Unknown feature flag key: surprise"):
        get_feature_flag_spec("surprise")


def test_constructor_and_snapshot_shape_match_canonical_metadata(monkeypatch):
    _clear_feature_flag_environment(monkeypatch)
    specs = get_feature_flag_specs()
    parameters = inspect.signature(FeatureFlags).parameters

    assert tuple(parameters) == tuple(spec.key for spec in specs)
    assert all(parameter.default is None for parameter in parameters.values())

    snapshot = FeatureFlags().snapshot()
    assert tuple(snapshot) == tuple(spec.key for spec in specs)
    assert snapshot == canonical_feature_flag_defaults()


def test_canonical_defaults_helper_returns_a_fresh_mapping():
    first = canonical_feature_flag_defaults()
    first["use_hypergraph"] = False

    assert canonical_feature_flag_defaults()["use_hypergraph"] is True


@pytest.mark.parametrize(
    "spec",
    get_feature_flag_specs(),
    ids=lambda spec: spec.key,
)
def test_every_primary_environment_name_resolves_from_metadata(monkeypatch, spec):
    _clear_feature_flag_environment(monkeypatch)
    raw_value, expected = _environment_sample(spec)
    monkeypatch.setenv(spec.env_name, raw_value)

    actual = FeatureFlags().snapshot()[spec.key]

    assert actual == expected
    assert type(actual) is spec.value_type


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    (
        ("true", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("no", False),
    ),
)
def test_supported_boolean_spellings_are_preserved(monkeypatch, raw_value, expected):
    _clear_feature_flag_environment(monkeypatch)
    monkeypatch.setenv("INFERRA_USE_HYPERGRAPH", raw_value)

    assert FeatureFlags().use_hypergraph is expected


def test_legacy_suffix_input_to_environment_helper_is_preserved(monkeypatch):
    monkeypatch.setenv("INFERRA_USE_HYPERGRAPH", "false")

    assert FeatureFlags._env_bool("USE_HYPERGRAPH", True) is False


def test_unrecognized_boolean_value_preserves_the_canonical_default(monkeypatch):
    _clear_feature_flag_environment(monkeypatch)
    monkeypatch.setenv("INFERRA_USE_HYPERGRAPH", "surprise")

    assert FeatureFlags().use_hypergraph is True


def test_question_strategy_compatibility_alias_and_primary_precedence(monkeypatch):
    _clear_feature_flag_environment(monkeypatch)
    monkeypatch.setenv("INFERRA_ONTOLOGY_QUESTION_STRATEGY", "true")

    assert FeatureFlags().ontology_question_strategy is True

    monkeypatch.setenv("INFERRA_ONTOLOGY_QUESTION_STRATEGY_ENABLED", "false")

    assert FeatureFlags().ontology_question_strategy is False


@pytest.mark.parametrize(
    ("key", "environment_value", "explicit_value"),
    (
        ("use_hypergraph", "true", False),
        ("ontology_reasoning_confidence_threshold", "0.1", 0.7),
        ("ontology_reasoning_max_closure_depth", "2", 7),
    ),
)
def test_constructor_precedes_environment_for_each_value_type(
    monkeypatch,
    key,
    environment_value,
    explicit_value,
):
    _clear_feature_flag_environment(monkeypatch)
    spec = next(spec for spec in get_feature_flag_specs() if spec.key == key)
    monkeypatch.setenv(spec.env_name, environment_value)

    flags = FeatureFlags(**{key: explicit_value})

    assert flags.snapshot()[key] == explicit_value


@pytest.mark.parametrize(
    ("env_name", "raw_value", "message"),
    (
        (
            "INFERRA_ONTOLOGY_REASONING_CONFIDENCE_THRESHOLD",
            "not-a-number",
            "must be a valid float",
        ),
        (
            "INFERRA_ONTOLOGY_REASONING_MIN_HIERARCHY_DEPTH",
            "1.5",
            "must be a valid integer",
        ),
        (
            "INFERRA_ONTOLOGY_AUTO_ANSWER_CONFIDENCE_THRESHOLD",
            "1.01",
            "must be less than or equal to 1.0",
        ),
        (
            "INFERRA_ONTOLOGY_REASONING_MIN_HIERARCHY_DEPTH",
            "-1",
            "must be greater than or equal to 0",
        ),
    ),
)
def test_invalid_numeric_environment_values_fail_fast(
    monkeypatch,
    env_name,
    raw_value,
    message,
):
    _clear_feature_flag_environment(monkeypatch)
    monkeypatch.setenv(env_name, raw_value)

    with pytest.raises(ValueError, match=message):
        FeatureFlags()


def test_numeric_constructor_values_are_typed_and_range_checked():
    flags = FeatureFlags(
        ontology_auto_answer_confidence_threshold=0,
        ontology_reasoning_confidence_threshold=1,
        ontology_reasoning_min_hierarchy_depth=0,
        ontology_reasoning_max_closure_depth=0,
    )

    assert flags.ontology_auto_answer_confidence_threshold == 0.0
    assert type(flags.ontology_auto_answer_confidence_threshold) is float
    assert flags.ontology_reasoning_confidence_threshold == 1.0

    with pytest.raises(TypeError, match="must be a float"):
        FeatureFlags(ontology_reasoning_confidence_threshold="0.5")
    with pytest.raises(TypeError, match="must be an integer"):
        FeatureFlags(ontology_reasoning_min_hierarchy_depth=1.5)
    with pytest.raises(ValueError, match="must be finite"):
        FeatureFlags(ontology_reasoning_confidence_threshold=float("nan"))


def test_maximum_closure_depth_cannot_be_below_minimum_hierarchy_depth():
    with pytest.raises(
        ValueError,
        match=(
            "ontology_reasoning_max_closure_depth must be greater than or equal to "
            "ontology_reasoning_min_hierarchy_depth"
        ),
    ):
        FeatureFlags(
            ontology_reasoning_min_hierarchy_depth=4,
            ontology_reasoning_max_closure_depth=3,
        )


def test_all_metadata_entries_are_sticky_in_one_frozen_snapshot(monkeypatch):
    _clear_feature_flag_environment(monkeypatch)
    overrides = {
        spec.key: _environment_sample(spec)[1]
        for spec in get_feature_flag_specs()
    }
    flags = FeatureFlags(**overrides)
    flags.freeze()

    for spec in get_feature_flag_specs():
        monkeypatch.setenv(spec.env_name, _default_text(spec.default))

    assert flags.is_frozen() is True
    assert flags.snapshot() == overrides
    assert {
        spec.key: getattr(flags, spec.key)
        for spec in get_feature_flag_specs()
    } == overrides


def test_effective_snapshot_helper_returns_a_copy(monkeypatch):
    flags = FeatureFlags(use_hypergraph=False)
    monkeypatch.setattr(feature_flags_module, "_default_flags", flags)

    snapshot = get_effective_feature_flag_snapshot()
    snapshot["use_hypergraph"] = True

    assert get_effective_feature_flag_snapshot()["use_hypergraph"] is False


def test_ontology_helpers_cover_empty_profile_and_metadata_snapshot():
    flags = FeatureFlags(
        ontology_advisory_enabled=True,
        ontology_auto_answer=True,
        ontology_reasoning=False,
        ontology_question_strategy=True,
    )

    assert normalize_ontology_profile(None) is None
    assert normalize_ontology_profile("  ") is None
    assert ontology_flags_snapshot(flags) == {
        "ontology_advisory_enabled": True,
        "ontology_auto_answer": True,
        "ontology_reasoning": False,
        "ontology_question_strategy": True,
    }


def test_duplicate_runtime_defaults_match_canonical_metadata(monkeypatch):
    context_defaults = {field.name: field.default for field in fields(InferenceContext)}
    reasoner_parameters = inspect.signature(OntologyReasoner).parameters
    router_parameters = inspect.signature(ReasoningRouter).parameters

    assert context_defaults["ontology_reasoning_confidence_threshold"] == get_feature_flag_default(
        "ontology_reasoning_confidence_threshold"
    )
    assert context_defaults["ontology_reasoning_min_hierarchy_depth"] == get_feature_flag_default(
        "ontology_reasoning_min_hierarchy_depth"
    )
    assert context_defaults["ontology_reasoning_max_closure_depth"] == get_feature_flag_default(
        "ontology_reasoning_max_closure_depth"
    )
    assert reasoner_parameters["confidence_threshold"].default == get_feature_flag_default(
        "ontology_reasoning_confidence_threshold"
    )
    assert reasoner_parameters["min_hierarchy_depth"].default == get_feature_flag_default(
        "ontology_reasoning_min_hierarchy_depth"
    )
    assert reasoner_parameters["max_closure_depth"].default == get_feature_flag_default(
        "ontology_reasoning_max_closure_depth"
    )
    assert router_parameters["abduction_enabled"].default == get_feature_flag_default(
        "abduction_enabled"
    )
    assert router_parameters["induction_pipeline"].default == get_feature_flag_default(
        "induction_pipeline"
    )
    assert router_parameters["confidence_thresholds"].default == get_feature_flag_default(
        "confidence_thresholds"
    )

    monkeypatch.setenv("INFERRA_ENV", "production")
    monkeypatch.delenv("INFERRA_AUTH_ENABLED", raising=False)
    monkeypatch.setattr(auth_middleware, "_configured_secret", lambda _name: True)
    if get_feature_flag_default("auth_enabled"):
        auth_middleware.assert_production_auth_config()
    else:
        with pytest.raises(RuntimeError, match="requires INFERRA_AUTH_ENABLED=true"):
            auth_middleware.assert_production_auth_config()


def test_module_header_defaults_match_canonical_metadata():
    documented = {
        f"INFERRA_{match.group('name')}": match.group("default")
        for match in re.finditer(
            r"^- (?P<name>[A-Z0-9_]+): .* \(default: (?P<default>[^)]+)\)$",
            feature_flags_module.__doc__ or "",
            re.MULTILINE,
        )
    }
    expected = {
        spec.env_name: _default_text(spec.default)
        for spec in get_feature_flag_specs()
    }

    assert documented == expected


def test_implementation_guide_phase_tables_match_canonical_metadata():
    guide = (ROOT / "IMPLEMENTATION_GUIDE.md").read_text(encoding="utf-8")
    phase_section = guide.split("## 2. Phases & Feature Flags", 1)[1].split(
        "### Code Defaults vs Overrides",
        1,
    )[0]
    documented = {}
    current_phase = None
    for line in phase_section.splitlines():
        heading = re.match(r"^### Phase (?P<phase>[1-5])\b", line)
        if heading:
            current_phase = int(heading.group("phase"))
            continue
        row = re.match(
            r"^\| `(?P<name>[A-Z0-9_]+)` \| `(?P<default>[^`]+)` \|",
            line,
        )
        if row:
            documented[f"INFERRA_{row.group('name')}"] = (
                current_phase,
                row.group("default"),
            )

    expected = {
        spec.env_name: (spec.phase, _default_text(spec.default))
        for spec in get_feature_flag_specs()
    }

    assert documented == expected


def test_implementation_guide_defaults_block_matches_canonical_metadata():
    guide = (ROOT / "IMPLEMENTATION_GUIDE.md").read_text(encoding="utf-8")
    defaults_section = guide.split("# Feature Flags (defaults shown)", 1)[1].split(
        "# Security (when AUTH_ENABLED=true)",
        1,
    )[0]
    documented = dict(
        re.findall(r"^(INFERRA_[A-Z0-9_]+)=([^\s#]+)$", defaults_section, re.MULTILINE)
    )
    expected = {
        spec.env_name: _default_text(spec.default)
        for spec in get_feature_flag_specs()
    }

    assert documented == expected


def test_readme_points_to_the_complete_canonical_inventory():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "IMPLEMENTATION_GUIDE.md#2-phases--feature-flags" in readme
    assert "complete canonical inventory and code defaults" in readme


def test_env_example_canonical_reference_matches_metadata():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    canonical_section = env_example.split(
        "# Canonical feature-flag code defaults (reference only).",
        1,
    )[1].split("# Feature-rich local/staging Compose overrides.", 1)[0]
    documented = dict(
        re.findall(
            r"^# (INFERRA_[A-Z0-9_]+)=([^\s#]+)$",
            canonical_section,
            re.MULTILINE,
        )
    )
    expected = {
        spec.env_name: _default_text(spec.default)
        for spec in get_feature_flag_specs()
    }

    assert documented == expected


def test_compose_uses_one_complete_api_worker_feature_profile():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    profile_section = compose.split(
        "x-feature-flag-profile: &feature-flag-profile",
        1,
    )[1].split("\nservices:", 1)[0]
    rows = re.findall(
        r"^  (INFERRA_[A-Z0-9_]+): \$\{(INFERRA_[A-Z0-9_]+):-([^}]+)\}$",
        profile_section,
        re.MULTILINE,
    )
    profile_defaults = {name: default for name, variable, default in rows}

    assert all(name == variable for name, variable, _default in rows)
    assert set(profile_defaults) == {
        spec.env_name
        for spec in get_feature_flag_specs()
    }
    assert compose.count("<<: *feature-flag-profile") == 2
    assert compose.count('INFERRA_LOAD_DOTENV: "false"') == 2
    assert profile_defaults["INFERRA_USE_HYPERGRAPH"] == "true"
    assert profile_defaults["INFERRA_LAYERED_MEMORY"] == "true"
    assert profile_defaults["INFERRA_STRICT_PORT_CONTRACTS"] == "true"
    assert profile_defaults["INFERRA_ASYNC_POST_REASONING"] == "true"
    assert profile_defaults["INFERRA_GENERATE_POST_REASONING_TTL"] == "true"


def test_env_example_labels_and_enables_the_complete_post_reasoning_profile():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    override_section = env_example.split(
        "# Feature-rich local/staging Compose overrides.",
        1,
    )[1].split("INFERRA_API_KEY=", 1)[0]

    assert "# Feature-rich local/staging Compose overrides." in env_example
    assert "INFERRA_ASYNC_POST_REASONING=true" in override_section
    assert "INFERRA_GENERATE_POST_REASONING_TTL=true" in override_section
    assert "workflow is never half-enabled" in override_section


def test_env_example_local_overrides_match_compose_profile_differences():
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    override_section = env_example.split(
        "# Feature-rich local/staging Compose overrides.",
        1,
    )[1].split("INFERRA_API_KEY=", 1)[0]
    documented_overrides = dict(
        re.findall(
            r"^(INFERRA_[A-Z0-9_]+)=([^\s#]+)$",
            override_section,
            re.MULTILINE,
        )
    )

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    profile_section = compose.split(
        "x-feature-flag-profile: &feature-flag-profile",
        1,
    )[1].split("\nservices:", 1)[0]
    profile_defaults = dict(
        re.findall(
            r"^  (INFERRA_[A-Z0-9_]+): \$\{INFERRA_[A-Z0-9_]+:-([^}]+)\}$",
            profile_section,
            re.MULTILINE,
        )
    )
    canonical_defaults = {
        spec.env_name: _default_text(spec.default)
        for spec in get_feature_flag_specs()
    }
    expected_overrides = {
        env_name: value
        for env_name, value in profile_defaults.items()
        if value != canonical_defaults[env_name]
    }

    assert documented_overrides == expected_overrides


def test_production_overlay_marks_both_application_processes_as_production():
    production_compose = (ROOT / "docker-compose.prod.yml").read_text(
        encoding="utf-8"
    )

    assert production_compose.count("INFERRA_ENV: production") == 2
