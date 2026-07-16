"""
Feature flag configuration for INFERRA.

Phase 1 feature flags:
- USE_HYPERGRAPH: Use HyperAdjacencyGraph instead of DependencyMatrix (default: true)
- LEGACY_ITERATE: Use nested InferenceEngine for iterate (default: true)
- LAYERED_MEMORY: Use LayeredFactStore for working memory (default: true)
- ML_OPTIMIZED_DFS: Use DFS topo-sort with HistoryRecord (default: false)

Phase 2 feature flags:
- ASYNC_SYNC_ENABLED: Enable async RuleUpdated → Celery → Fuseki pipeline (default: false)
- MODULAR_IMPORTS: Enable IMPORT: / RULE SET: tokens with RuleSetImportResolver (default: false)

Phase 3 feature flags:
- HYBRID_ORCHESTRATOR: Enable BackwardChainOrchestrator wrapper (default: false)
- ASYNC_POST_REASONING: Enable async ontology post-reasoning events (default: false)
- GENERATE_POST_REASONING_TTL: Generate post-reasoning TTL artifacts (default: false)
- PROV_O_TRACE: Enable PROV-O trace generation (default: false)
- ENRICHED_API: Enable provenance-enriched API responses (default: false)
- ONTOLOGY_ADVISORY_ENABLED: Enable session-scoped ontology advisory suggestions (default: false)
- ONTOLOGY_AUTO_ANSWER_ENABLED: Enable session-scoped ontology default auto-answers (default: false)
- ONTOLOGY_AUTO_ANSWER_CONFIDENCE_THRESHOLD: Minimum auto-answer confidence (default: 0.85)
- ONTOLOGY_REASONING_ENABLED: Enable materialized ontology reasoning into INFERRED (default: false)
- ONTOLOGY_REASONING_CONFIDENCE_THRESHOLD: Minimum materialization confidence (default: 0.85)
- ONTOLOGY_REASONING_MIN_HIERARCHY_DEPTH: Minimum hierarchy depth (default: 1)
- ONTOLOGY_REASONING_MAX_CLOSURE_DEPTH: Maximum ontology closure depth (default: 10)
- ONTOLOGY_QUESTION_STRATEGY_ENABLED: Enable semantic question ordering/pruning hints (default: false)

Phase 4 feature flags:
- REDIS_SESSION_STORE: Enable Redis-backed session storage (default: false)
- LLM_ENHANCEMENTS: Enable LLM goal mapping/explanation adapters (default: false)
- STRICT_PORT_CONTRACTS: Enforce strict port-contract checks (default: true)
- OBSERVABILITY_ENABLED: Enable observability integrations (default: false)
- AUTH_ENABLED: Enable auth middleware (default: false)

Phase 5 feature flags:
- ABDUCTION_ENABLED: Enable abduction adapters (default: false)
- INDUCTION_PIPELINE: Enable induction batch pipeline (default: false)
- REASONING_ROUTER: Enable hybrid reasoning router (default: true)
- CONFIDENCE_THRESHOLDS: Enable hypothesis confidence gates (default: true)

Feature flags are start-of-session sticky — cannot flip mid-session.
"""

import hashlib
import json
import math
import os
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional, Tuple, Union


FeatureFlagValue = Union[bool, float, int]


class FeatureFlagSnapshotMismatchError(RuntimeError):
    """Raised when two cooperating processes use different flag snapshots."""


@dataclass(frozen=True)
class FeatureFlagSpec:
    """Immutable canonical metadata for one flag or typed feature setting."""

    key: str
    env_name: str
    value_type: type
    default: FeatureFlagValue
    phase: int
    description: str
    minimum: Optional[Union[float, int]] = None
    maximum: Optional[Union[float, int]] = None
    minimum_from_key: Optional[str] = None
    aliases: Tuple[str, ...] = ()
    session_sticky: bool = True

    def __post_init__(self) -> None:
        if not self.key or self.key != self.key.lower():
            raise ValueError("Feature flag keys must be non-empty lowercase names")
        if not self.env_name.startswith("INFERRA_"):
            raise ValueError(
                f"Feature flag environment name must start with INFERRA_: {self.env_name}"
            )
        if self.value_type not in (bool, float, int):
            raise TypeError(
                f"Unsupported feature flag type for {self.key}: {self.value_type!r}"
            )
        if type(self.default) is not self.value_type:
            raise TypeError(
                f"Default for {self.key} must be {self.value_type.__name__}, "
                f"got {type(self.default).__name__}"
            )
        if self.phase not in (1, 2, 3, 4, 5):
            raise ValueError(f"Unsupported feature flag phase for {self.key}: {self.phase}")
        if not self.description.strip():
            raise ValueError(f"Feature flag description must not be empty: {self.key}")
        if self.value_type is bool and (
            self.minimum is not None or self.maximum is not None
        ):
            raise TypeError(f"Boolean feature flag cannot have numeric bounds: {self.key}")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError(f"Feature flag minimum exceeds maximum: {self.key}")
        if self.minimum_from_key is not None and not self.minimum_from_key:
            raise ValueError(
                f"Feature flag minimum reference must not be empty: {self.key}"
            )
        if any(not alias.startswith("INFERRA_") for alias in self.aliases):
            raise ValueError(f"Feature flag aliases must start with INFERRA_: {self.key}")

    @property
    def environment_names(self) -> Tuple[str, ...]:
        """Return the primary environment name followed by compatibility aliases."""
        return (self.env_name, *self.aliases)


ONTOLOGY_PROFILE_FLAG_KEYS = (
    "ontology_advisory_enabled",
    "ontology_auto_answer",
    "ontology_reasoning",
    "ontology_question_strategy",
)

ONTOLOGY_ASSISTANCE_PROFILES: Mapping[str, Mapping[str, bool]] = {
    "off": {
        "ontology_advisory_enabled": False,
        "ontology_auto_answer": False,
        "ontology_reasoning": False,
        "ontology_question_strategy": False,
    },
    "advisory": {
        "ontology_advisory_enabled": True,
        "ontology_auto_answer": False,
        "ontology_reasoning": False,
        "ontology_question_strategy": False,
    },
    "auto_answer": {
        "ontology_advisory_enabled": True,
        "ontology_auto_answer": True,
        "ontology_reasoning": False,
        "ontology_question_strategy": False,
    },
    "reasoning": {
        "ontology_advisory_enabled": True,
        "ontology_auto_answer": True,
        "ontology_reasoning": True,
        "ontology_question_strategy": False,
    },
    "full_semantic_pilot": {
        "ontology_advisory_enabled": True,
        "ontology_auto_answer": True,
        "ontology_reasoning": True,
        "ontology_question_strategy": True,
    },
}

ONTOLOGY_FLAG_ALIASES = {
    "advisory_enabled": "ontology_advisory_enabled",
    "ontology_advisory_enabled": "ontology_advisory_enabled",
    "auto_answer": "ontology_auto_answer",
    "auto_answer_enabled": "ontology_auto_answer",
    "ontology_auto_answer": "ontology_auto_answer",
    "reasoning": "ontology_reasoning",
    "reasoning_enabled": "ontology_reasoning",
    "ontology_reasoning": "ontology_reasoning",
    "question_strategy": "ontology_question_strategy",
    "question_strategy_enabled": "ontology_question_strategy",
    "ontology_question_strategy": "ontology_question_strategy",
}


FEATURE_FLAG_SPECS: Tuple[FeatureFlagSpec, ...] = (
    FeatureFlagSpec(
        key="use_hypergraph",
        env_name="INFERRA_USE_HYPERGRAPH",
        value_type=bool,
        default=True,
        phase=1,
        description="Use HyperAdjacencyGraph instead of DependencyMatrix.",
    ),
    FeatureFlagSpec(
        key="legacy_iterate",
        env_name="INFERRA_LEGACY_ITERATE",
        value_type=bool,
        default=True,
        phase=1,
        description="Use the nested InferenceEngine iterate compatibility path.",
    ),
    FeatureFlagSpec(
        key="layered_memory",
        env_name="INFERRA_LAYERED_MEMORY",
        value_type=bool,
        default=True,
        phase=1,
        description="Use LayeredFactStore for provenance-aware working memory.",
    ),
    FeatureFlagSpec(
        key="ml_optimized_dfs",
        env_name="INFERRA_ML_OPTIMIZED_DFS",
        value_type=bool,
        default=False,
        phase=1,
        description="Use history-aware DFS topological ordering.",
    ),
    FeatureFlagSpec(
        key="async_sync_enabled",
        env_name="INFERRA_ASYNC_SYNC_ENABLED",
        value_type=bool,
        default=False,
        phase=2,
        description="Enable the asynchronous RuleUpdated to Celery to Fuseki pipeline.",
    ),
    FeatureFlagSpec(
        key="modular_imports",
        env_name="INFERRA_MODULAR_IMPORTS",
        value_type=bool,
        default=False,
        phase=2,
        description="Enable IMPORT and RULE SET resolution.",
    ),
    FeatureFlagSpec(
        key="hybrid_orchestrator",
        env_name="INFERRA_HYBRID_ORCHESTRATOR",
        value_type=bool,
        default=False,
        phase=3,
        description="Enable the BackwardChainOrchestrator convergence wrapper.",
    ),
    FeatureFlagSpec(
        key="async_post_reasoning",
        env_name="INFERRA_ASYNC_POST_REASONING",
        value_type=bool,
        default=False,
        phase=3,
        description="Enable asynchronous ontology post-reasoning events.",
    ),
    FeatureFlagSpec(
        key="generate_post_reasoning_ttl",
        env_name="INFERRA_GENERATE_POST_REASONING_TTL",
        value_type=bool,
        default=False,
        phase=3,
        description="Generate post-reasoning TTL artifacts.",
    ),
    FeatureFlagSpec(
        key="prov_o_trace",
        env_name="INFERRA_PROV_O_TRACE",
        value_type=bool,
        default=False,
        phase=3,
        description="Enable W3C PROV-O trace generation.",
    ),
    FeatureFlagSpec(
        key="enriched_api",
        env_name="INFERRA_ENRICHED_API",
        value_type=bool,
        default=False,
        phase=3,
        description="Enable provenance-enriched API responses.",
    ),
    FeatureFlagSpec(
        key="ontology_advisory_enabled",
        env_name="INFERRA_ONTOLOGY_ADVISORY_ENABLED",
        value_type=bool,
        default=False,
        phase=3,
        description="Enable session-scoped ontology advisory suggestions.",
    ),
    FeatureFlagSpec(
        key="ontology_auto_answer",
        env_name="INFERRA_ONTOLOGY_AUTO_ANSWER_ENABLED",
        value_type=bool,
        default=False,
        phase=3,
        description="Enable session-scoped ontology default auto-answers.",
    ),
    FeatureFlagSpec(
        key="ontology_auto_answer_confidence_threshold",
        env_name="INFERRA_ONTOLOGY_AUTO_ANSWER_CONFIDENCE_THRESHOLD",
        value_type=float,
        default=0.85,
        phase=3,
        description="Set the minimum ontology auto-answer confidence.",
        minimum=0.0,
        maximum=1.0,
    ),
    FeatureFlagSpec(
        key="ontology_reasoning",
        env_name="INFERRA_ONTOLOGY_REASONING_ENABLED",
        value_type=bool,
        default=False,
        phase=3,
        description="Enable materialized ontology reasoning into INFERRED facts.",
    ),
    FeatureFlagSpec(
        key="ontology_reasoning_confidence_threshold",
        env_name="INFERRA_ONTOLOGY_REASONING_CONFIDENCE_THRESHOLD",
        value_type=float,
        default=0.85,
        phase=3,
        description="Set the minimum ontology materialization confidence.",
        minimum=0.0,
        maximum=1.0,
    ),
    FeatureFlagSpec(
        key="ontology_reasoning_min_hierarchy_depth",
        env_name="INFERRA_ONTOLOGY_REASONING_MIN_HIERARCHY_DEPTH",
        value_type=int,
        default=1,
        phase=3,
        description="Set the minimum ontology hierarchy depth.",
        minimum=0,
    ),
    FeatureFlagSpec(
        key="ontology_reasoning_max_closure_depth",
        env_name="INFERRA_ONTOLOGY_REASONING_MAX_CLOSURE_DEPTH",
        value_type=int,
        default=10,
        phase=3,
        description="Set the maximum ontology closure depth.",
        minimum=0,
        minimum_from_key="ontology_reasoning_min_hierarchy_depth",
    ),
    FeatureFlagSpec(
        key="ontology_question_strategy",
        env_name="INFERRA_ONTOLOGY_QUESTION_STRATEGY_ENABLED",
        value_type=bool,
        default=False,
        phase=3,
        description="Enable semantic question ordering and pruning hints.",
        aliases=("INFERRA_ONTOLOGY_QUESTION_STRATEGY",),
    ),
    FeatureFlagSpec(
        key="redis_session_store",
        env_name="INFERRA_REDIS_SESSION_STORE",
        value_type=bool,
        default=False,
        phase=4,
        description="Enable Redis-backed session storage.",
    ),
    FeatureFlagSpec(
        key="llm_enhancements",
        env_name="INFERRA_LLM_ENHANCEMENTS",
        value_type=bool,
        default=False,
        phase=4,
        description="Enable LLM goal-mapping and explanation adapters.",
    ),
    FeatureFlagSpec(
        key="strict_port_contracts",
        env_name="INFERRA_STRICT_PORT_CONTRACTS",
        value_type=bool,
        default=True,
        phase=4,
        description="Enable strict port-contract checks.",
    ),
    FeatureFlagSpec(
        key="observability_enabled",
        env_name="INFERRA_OBSERVABILITY_ENABLED",
        value_type=bool,
        default=False,
        phase=4,
        description="Enable observability integrations.",
    ),
    FeatureFlagSpec(
        key="auth_enabled",
        env_name="INFERRA_AUTH_ENABLED",
        value_type=bool,
        default=False,
        phase=4,
        description="Enable authentication middleware.",
    ),
    FeatureFlagSpec(
        key="abduction_enabled",
        env_name="INFERRA_ABDUCTION_ENABLED",
        value_type=bool,
        default=False,
        phase=5,
        description="Enable abduction adapters.",
    ),
    FeatureFlagSpec(
        key="induction_pipeline",
        env_name="INFERRA_INDUCTION_PIPELINE",
        value_type=bool,
        default=False,
        phase=5,
        description="Enable the induction batch pipeline.",
    ),
    FeatureFlagSpec(
        key="reasoning_router",
        env_name="INFERRA_REASONING_ROUTER",
        value_type=bool,
        default=True,
        phase=5,
        description="Enable the hybrid reasoning router.",
    ),
    FeatureFlagSpec(
        key="confidence_thresholds",
        env_name="INFERRA_CONFIDENCE_THRESHOLDS",
        value_type=bool,
        default=True,
        phase=5,
        description="Enable hypothesis confidence gates.",
    ),
)

EXPECTED_FEATURE_FLAG_COUNT = 28
if len(FEATURE_FLAG_SPECS) != EXPECTED_FEATURE_FLAG_COUNT:
    raise RuntimeError(
        f"Expected {EXPECTED_FEATURE_FLAG_COUNT} canonical feature flag entries, "
        f"found {len(FEATURE_FLAG_SPECS)}"
    )

FEATURE_FLAG_SPEC_BY_KEY: Mapping[str, FeatureFlagSpec] = MappingProxyType(
    {spec.key: spec for spec in FEATURE_FLAG_SPECS}
)
if len(FEATURE_FLAG_SPEC_BY_KEY) != len(FEATURE_FLAG_SPECS):
    raise RuntimeError("Canonical feature flag snapshot keys must be unique")
if any(
    spec.minimum_from_key not in FEATURE_FLAG_SPEC_BY_KEY
    for spec in FEATURE_FLAG_SPECS
    if spec.minimum_from_key is not None
):
    raise RuntimeError("Feature flag numeric constraint references an unknown key")

_PRIMARY_ENV_NAMES = tuple(spec.env_name for spec in FEATURE_FLAG_SPECS)
if len(set(_PRIMARY_ENV_NAMES)) != len(_PRIMARY_ENV_NAMES):
    raise RuntimeError("Canonical feature flag environment names must be unique")

_ALL_ENV_NAMES = tuple(
    env_name
    for spec in FEATURE_FLAG_SPECS
    for env_name in spec.environment_names
)
if len(set(_ALL_ENV_NAMES)) != len(_ALL_ENV_NAMES):
    raise RuntimeError("Feature flag primary environment names and aliases must be unique")


# These switches remain in the compatibility snapshot for one migration
# window, but the current graph-first runtime cannot safely run with them off.
# STRICT_PORT_CONTRACTS is likewise an invariant while the runtime switch is
# retired in favour of unconditional CI architecture checks.
REQUIRED_TRUE_RUNTIME_FLAGS: Mapping[str, str] = MappingProxyType(
    {
        "use_hypergraph": "HyperAdjacencyGraph is the canonical runtime graph",
        "layered_memory": "Phase 2+ truth maintenance requires LayeredFactStore",
        "strict_port_contracts": "port contracts are enforced unconditionally",
    }
)

COUPLED_RUNTIME_FLAG_GROUPS: Tuple[Tuple[str, ...], ...] = (
    ("async_post_reasoning", "generate_post_reasoning_ttl"),
)


def get_feature_flag_specs() -> Tuple[FeatureFlagSpec, ...]:
    """Return the immutable canonical feature-flag metadata in snapshot order."""
    return FEATURE_FLAG_SPECS


def get_feature_flag_spec(key: str) -> FeatureFlagSpec:
    """Return canonical metadata for one snapshot key."""
    try:
        return FEATURE_FLAG_SPEC_BY_KEY[key]
    except KeyError as exc:
        raise KeyError(f"Unknown feature flag key: {key}") from exc


def get_feature_flag_default(key: str) -> FeatureFlagValue:
    """Return the canonical no-environment code default for one snapshot key."""
    return get_feature_flag_spec(key).default


def canonical_feature_flag_defaults() -> dict[str, FeatureFlagValue]:
    """Return a fresh mapping of all canonical code defaults in snapshot order."""
    return {spec.key: spec.default for spec in FEATURE_FLAG_SPECS}


class FeatureFlags:
    """
    Feature flag configuration for INFERRA.

    Flags are read once at session start and remain fixed for the
    duration of that session. This ensures data consistency —
    flipping a flag mid-session could cause data incompatibilities
    (e.g., switching from matrix to graph mid-inference).
    """

    def __init__(
        self,
        use_hypergraph: Optional[bool] = None,
        legacy_iterate: Optional[bool] = None,
        layered_memory: Optional[bool] = None,
        ml_optimized_dfs: Optional[bool] = None,
        async_sync_enabled: Optional[bool] = None,
        modular_imports: Optional[bool] = None,
        hybrid_orchestrator: Optional[bool] = None,
        async_post_reasoning: Optional[bool] = None,
        generate_post_reasoning_ttl: Optional[bool] = None,
        prov_o_trace: Optional[bool] = None,
        enriched_api: Optional[bool] = None,
        ontology_advisory_enabled: Optional[bool] = None,
        ontology_auto_answer: Optional[bool] = None,
        ontology_auto_answer_confidence_threshold: Optional[float] = None,
        ontology_reasoning: Optional[bool] = None,
        ontology_reasoning_confidence_threshold: Optional[float] = None,
        ontology_reasoning_min_hierarchy_depth: Optional[int] = None,
        ontology_reasoning_max_closure_depth: Optional[int] = None,
        ontology_question_strategy: Optional[bool] = None,
        redis_session_store: Optional[bool] = None,
        llm_enhancements: Optional[bool] = None,
        strict_port_contracts: Optional[bool] = None,
        observability_enabled: Optional[bool] = None,
        auth_enabled: Optional[bool] = None,
        abduction_enabled: Optional[bool] = None,
        induction_pipeline: Optional[bool] = None,
        reasoning_router: Optional[bool] = None,
        confidence_thresholds: Optional[bool] = None,
    ):
        constructor_values = locals().copy()
        for spec in FEATURE_FLAG_SPECS:
            explicit_value = constructor_values[spec.key]
            resolved_value = (
                explicit_value
                if explicit_value is not None
                else self._value_from_environment(spec)
            )
            setattr(
                self,
                f"_{spec.key}",
                self._validated_value(spec, resolved_value),
            )
        self._validate_cross_setting_constraints()
        self._frozen = False

    @classmethod
    def _value_from_environment(cls, spec: FeatureFlagSpec) -> FeatureFlagValue:
        """Resolve one metadata entry using its primary name and aliases."""
        if spec.value_type is bool:
            return cls._env_bool_any(spec.environment_names, bool(spec.default))
        if spec.value_type is float:
            return cls._env_float(spec.env_name, float(spec.default))
        if spec.value_type is int:
            return cls._env_int(spec.env_name, int(spec.default))
        raise TypeError(
            f"Unsupported feature flag type for {spec.key}: {spec.value_type!r}"
        )

    @staticmethod
    def _validated_value(
        spec: FeatureFlagSpec,
        value: FeatureFlagValue,
    ) -> FeatureFlagValue:
        """Normalize and validate one resolved value against canonical metadata."""
        if spec.value_type is bool:
            return value
        if spec.value_type is float:
            if isinstance(value, bool) or not isinstance(value, (float, int)):
                raise TypeError(f"{spec.key} must be a float")
            normalized: FeatureFlagValue = float(value)
            if not math.isfinite(normalized):
                raise ValueError(f"{spec.key} must be finite")
        elif spec.value_type is int:
            if type(value) is not int:
                raise TypeError(f"{spec.key} must be an integer")
            normalized = value
        else:
            raise TypeError(
                f"Unsupported feature flag type for {spec.key}: {spec.value_type!r}"
            )

        if spec.minimum is not None and normalized < spec.minimum:
            raise ValueError(
                f"{spec.key} must be greater than or equal to {spec.minimum}"
            )
        if spec.maximum is not None and normalized > spec.maximum:
            raise ValueError(
                f"{spec.key} must be less than or equal to {spec.maximum}"
            )
        return normalized

    def _validate_cross_setting_constraints(self) -> None:
        for spec in FEATURE_FLAG_SPECS:
            if spec.minimum_from_key is None:
                continue
            value = getattr(self, f"_{spec.key}")
            minimum_value = getattr(self, f"_{spec.minimum_from_key}")
            if value < minimum_value:
                raise ValueError(
                    f"{spec.key} must be greater than or equal to "
                    f"{spec.minimum_from_key}"
                )

    @staticmethod
    def _qualified_env_name(name: str) -> str:
        """Accept legacy suffix inputs as well as canonical full environment names."""
        return name if name.startswith("INFERRA_") else f"INFERRA_{name}"

    @classmethod
    def _env_bool(cls, name: str, default: bool) -> bool:
        """Read a boolean from an environment variable."""
        val = os.environ.get(cls._qualified_env_name(name), "").lower()
        if val in ("true", "1", "yes"):
            return True
        if val in ("false", "0", "no"):
            return False
        return default

    @classmethod
    def _env_bool_any(cls, names: Tuple[str, ...], default: bool) -> bool:
        """Read a boolean from the first configured environment variable."""
        for name in names:
            raw = os.environ.get(cls._qualified_env_name(name), "")
            if raw:
                return cls._env_bool(name, default)
        return default

    @classmethod
    def _env_float(cls, name: str, default: float) -> float:
        """Read a float from an environment variable."""
        env_name = cls._qualified_env_name(name)
        val = os.environ.get(env_name, "")
        if not val:
            return default
        try:
            return float(val)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{env_name} must be a valid float, got {val!r}") from exc

    @classmethod
    def _env_int(cls, name: str, default: int) -> int:
        """Read an integer from an environment variable."""
        env_name = cls._qualified_env_name(name)
        val = os.environ.get(env_name, "")
        if not val:
            return default
        try:
            return int(val)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{env_name} must be a valid integer, got {val!r}") from exc

    @property
    def use_hypergraph(self) -> bool:
        return self._use_hypergraph

    @property
    def legacy_iterate(self) -> bool:
        return self._legacy_iterate

    @property
    def layered_memory(self) -> bool:
        return self._layered_memory

    @property
    def ml_optimized_dfs(self) -> bool:
        return self._ml_optimized_dfs

    @property
    def async_sync_enabled(self) -> bool:
        return self._async_sync_enabled

    @property
    def modular_imports(self) -> bool:
        return self._modular_imports

    @property
    def hybrid_orchestrator(self) -> bool:
        return self._hybrid_orchestrator

    @property
    def async_post_reasoning(self) -> bool:
        return self._async_post_reasoning

    @property
    def generate_post_reasoning_ttl(self) -> bool:
        return self._generate_post_reasoning_ttl

    @property
    def prov_o_trace(self) -> bool:
        return self._prov_o_trace

    @property
    def enriched_api(self) -> bool:
        return self._enriched_api

    @property
    def ontology_advisory_enabled(self) -> bool:
        return self._ontology_advisory_enabled

    @property
    def ontology_auto_answer(self) -> bool:
        return self._ontology_auto_answer

    @property
    def ontology_auto_answer_confidence_threshold(self) -> float:
        return self._ontology_auto_answer_confidence_threshold

    @property
    def ontology_reasoning(self) -> bool:
        return self._ontology_reasoning

    @property
    def ontology_reasoning_confidence_threshold(self) -> float:
        return self._ontology_reasoning_confidence_threshold

    @property
    def ontology_reasoning_min_hierarchy_depth(self) -> int:
        return self._ontology_reasoning_min_hierarchy_depth

    @property
    def ontology_reasoning_max_closure_depth(self) -> int:
        return self._ontology_reasoning_max_closure_depth

    @property
    def ontology_question_strategy(self) -> bool:
        return self._ontology_question_strategy

    @property
    def redis_session_store(self) -> bool:
        return self._redis_session_store

    @property
    def llm_enhancements(self) -> bool:
        return self._llm_enhancements

    @property
    def strict_port_contracts(self) -> bool:
        return self._strict_port_contracts

    @property
    def observability_enabled(self) -> bool:
        return self._observability_enabled

    @property
    def auth_enabled(self) -> bool:
        return self._auth_enabled

    @property
    def abduction_enabled(self) -> bool:
        return self._abduction_enabled

    @property
    def induction_pipeline(self) -> bool:
        return self._induction_pipeline

    @property
    def reasoning_router(self) -> bool:
        return self._reasoning_router

    @property
    def confidence_thresholds(self) -> bool:
        return self._confidence_thresholds

    def freeze(self) -> None:
        """Freeze flags for the current session. After freeze(), mutations are rejected."""
        self._frozen = True

    def is_frozen(self) -> bool:
        """Check if flags are frozen for the current session."""
        return self._frozen

    def snapshot(self) -> dict:
        """Return a snapshot of current flag values (for session metadata)."""
        return {
            spec.key: getattr(self, f"_{spec.key}")
            for spec in FEATURE_FLAG_SPECS
        }

    def legacy_retirement_report(self) -> dict:
        """Report legacy flags that must be frozen or retired before production."""
        return {
            "use_hypergraph": {
                "actual": self._use_hypergraph,
                "expected": True,
                "status": "required_on",
                "ready": self._use_hypergraph is True,
                "reason": "HyperAdjacencyGraph is the canonical runtime graph.",
            },
            "layered_memory": {
                "actual": self._layered_memory,
                "expected": True,
                "status": "required_on",
                "ready": self._layered_memory is True,
                "reason": "Phase 2+ truth-maintenance depends on LayeredFactStore.",
            },
            "legacy_iterate": {
                "actual": self._legacy_iterate,
                "expected": False,
                "status": "deprecated",
                "ready": self._legacy_iterate is False,
                "reason": "IterationEngine is the production path; legacy nested inference is compatibility only.",
            },
            "ml_optimized_dfs": {
                "actual": self._ml_optimized_dfs,
                "expected": "deployment_decision",
                "status": "optional_strategy",
                "ready": True,
                "reason": "MLTopologicalSortStrategy supports both deterministic DFS and history-aware ordering.",
            },
            "strict_port_contracts": {
                "actual": self._strict_port_contracts,
                "expected": True,
                "status": "retirement_pending",
                "ready": self._strict_port_contracts is True,
                "reason": "Port contracts are unconditional CI architecture gates; the runtime switch is retained for compatibility only.",
            },
        }


def validate_runtime_feature_flags(flags: FeatureFlags) -> FeatureFlags:
    """Fail fast when a process/session selects an unsupported flag profile.

    Direct ``FeatureFlags`` construction remains permissive for compatibility
    tests and snapshot migration. API/worker startup and inference-session
    creation call this guard before doing work.
    """
    violations = []
    for key, reason in REQUIRED_TRUE_RUNTIME_FLAGS.items():
        if getattr(flags, key) is not True:
            violations.append(f"{key} must be true: {reason}")

    for group in COUPLED_RUNTIME_FLAG_GROUPS:
        values = {getattr(flags, key) for key in group}
        if len(values) != 1:
            violations.append(
                f"{', '.join(group)} must be enabled or disabled together"
            )

    if violations:
        raise RuntimeError(
            "Invalid INFERRA feature flag runtime configuration: "
            + "; ".join(violations)
        )
    return flags


def normalize_ontology_profile(profile: Optional[str]) -> Optional[str]:
    """Normalize and validate an ontology assistance profile name."""
    if profile is None:
        return None
    normalized = profile.strip().lower().replace("-", "_")
    if not normalized:
        return None
    if normalized not in ONTOLOGY_ASSISTANCE_PROFILES:
        supported = ", ".join(sorted(ONTOLOGY_ASSISTANCE_PROFILES))
        raise ValueError(
            f"Unsupported ontology_profile '{profile}'. Supported profiles: {supported}"
        )
    return normalized


def infer_ontology_profile(snapshot: Mapping[str, Any]) -> str:
    """Infer a profile label from resolved ontology feature flags."""
    current = {
        key: bool(snapshot.get(key, False))
        for key in ONTOLOGY_PROFILE_FLAG_KEYS
    }
    for name, flags in ONTOLOGY_ASSISTANCE_PROFILES.items():
        if current == dict(flags):
            return name
    return "custom"


def normalize_ontology_flag_overrides(
    overrides: Optional[Mapping[str, Any]],
) -> dict:
    """Normalize per-session ontology flag overrides from API-friendly keys."""
    if not overrides:
        return {}
    normalized: dict[str, bool] = {}
    for key, value in overrides.items():
        target = ONTOLOGY_FLAG_ALIASES.get(str(key))
        if target is None:
            supported = ", ".join(sorted(ONTOLOGY_FLAG_ALIASES))
            raise ValueError(
                f"Unsupported ontology flag override '{key}'. Supported keys: {supported}"
            )
        normalized[target] = bool(value)
    return normalized


def feature_flags_from_snapshot(
    snapshot: Mapping[str, Any],
    *,
    ontology_profile: Optional[str] = None,
    ontology_flags: Optional[Mapping[str, Any]] = None,
) -> tuple[FeatureFlags, str]:
    """Build a FeatureFlags instance, optionally applying an ontology profile."""
    resolved = dict(snapshot)
    normalized_profile = normalize_ontology_profile(ontology_profile)
    if normalized_profile is not None:
        resolved.update(ONTOLOGY_ASSISTANCE_PROFILES[normalized_profile])
    resolved.update(normalize_ontology_flag_overrides(ontology_flags))
    selected_profile = infer_ontology_profile(resolved)
    if normalized_profile is not None and not ontology_flags:
        selected_profile = normalized_profile
    return FeatureFlags(**resolved), selected_profile


def ontology_flags_snapshot(flags: FeatureFlags) -> dict:
    """Return only the ontology assistance flag state for audit context."""
    snapshot = flags.snapshot()
    return {key: snapshot[key] for key in ONTOLOGY_PROFILE_FLAG_KEYS}


# Process-level flags are lazy so API and worker entry points can load their
# environment before the effective snapshot is constructed.
_default_flags: Optional[FeatureFlags] = None


def get_feature_flags() -> FeatureFlags:
    """Get the global feature flags instance."""
    global _default_flags
    if _default_flags is None:
        _default_flags = FeatureFlags()
    return _default_flags


def get_effective_feature_flag_snapshot() -> dict[str, FeatureFlagValue]:
    """Return a copy of the process-level effective feature-flag snapshot."""
    return get_feature_flags().snapshot()


def feature_flag_snapshot_hash(
    snapshot: Mapping[str, FeatureFlagValue],
) -> str:
    """Return a stable SHA-256 hash for one complete canonical snapshot."""
    expected_keys = tuple(spec.key for spec in FEATURE_FLAG_SPECS)
    missing = [key for key in expected_keys if key not in snapshot]
    unexpected = sorted(set(snapshot) - set(expected_keys))
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected)}")
        raise ValueError(
            "Feature flag snapshot must contain exactly the canonical keys ("
            + "; ".join(details)
            + ")"
        )

    canonical_payload = {
        key: snapshot[key]
        for key in expected_keys
    }
    encoded = json.dumps(
        canonical_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def get_effective_feature_flag_snapshot_hash() -> str:
    """Return the stable hash of the process-level effective snapshot."""
    return feature_flag_snapshot_hash(get_effective_feature_flag_snapshot())


def feature_flag_value_sources(
    flags: Optional[FeatureFlags] = None,
    *,
    environment: Optional[Mapping[str, str]] = None,
) -> dict[str, dict[str, Optional[str]]]:
    """Classify each effective value as environment, explicit, or code default."""
    effective_flags = flags or get_feature_flags()
    snapshot = effective_flags.snapshot()
    environment_values = environment if environment is not None else os.environ
    sources: dict[str, dict[str, Optional[str]]] = {}

    for spec in FEATURE_FLAG_SPECS:
        configured_name = next(
            (
                name
                for name in spec.environment_names
                if str(environment_values.get(name, ""))
            ),
            None,
        )
        if configured_name is not None:
            classification = "environment"
        elif snapshot[spec.key] != spec.default:
            classification = "explicit_override"
        else:
            classification = "code_default"
        sources[spec.key] = {
            "classification": classification,
            "environment_name": configured_name,
        }
    return sources


def build_effective_feature_flag_report(
    process_role: str,
    *,
    flags: Optional[FeatureFlags] = None,
    deployment_profile: Optional[str] = None,
    environment: Optional[Mapping[str, str]] = None,
) -> dict[str, Any]:
    """Build a redaction-safe process report from canonical flag metadata."""
    normalized_role = str(process_role).strip().lower()
    if not normalized_role:
        raise ValueError("process_role must not be empty")

    effective_flags = flags or get_feature_flags()
    snapshot = effective_flags.snapshot()
    environment_values = environment if environment is not None else os.environ
    selected_profile = (
        deployment_profile
        if deployment_profile is not None
        else environment_values.get("INFERRA_ENV", "")
    )
    normalized_profile = str(selected_profile or "unspecified").strip().lower()
    if not normalized_profile:
        normalized_profile = "unspecified"

    return {
        "schema_version": 1,
        "process_role": normalized_role,
        "deployment_profile": normalized_profile,
        "flag_count": len(FEATURE_FLAG_SPECS),
        "snapshot_hash": feature_flag_snapshot_hash(snapshot),
        "canonical_defaults": canonical_feature_flag_defaults(),
        "effective": snapshot,
        "sources": feature_flag_value_sources(
            effective_flags,
            environment=environment_values,
        ),
        "legacy_retirement": effective_flags.legacy_retirement_report(),
    }


def assert_feature_flag_snapshot_match(
    expected_snapshot_hash: Optional[str],
    *,
    flags: Optional[FeatureFlags] = None,
) -> str:
    """Reject a cross-process workflow when publisher and worker hashes differ.

    ``None`` remains accepted for tasks queued before hash propagation was
    introduced. All newly published tasks include the expected hash.
    """
    actual_snapshot_hash = feature_flag_snapshot_hash(
        (flags or get_feature_flags()).snapshot()
    )
    if (
        expected_snapshot_hash is not None
        and str(expected_snapshot_hash) != actual_snapshot_hash
    ):
        raise FeatureFlagSnapshotMismatchError(
            "INFERRA feature flag snapshot mismatch: "
            f"publisher={expected_snapshot_hash}, worker={actual_snapshot_hash}"
        )
    return actual_snapshot_hash


def reset_feature_flags(**overrides) -> FeatureFlags:
    """Create fresh feature flags (for testing or new sessions)."""
    return FeatureFlags(**overrides)
