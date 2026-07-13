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
- PROV_O_TRACE: Enable PROV-O trace generation (default: false)
- ENRICHED_API: Enable provenance-enriched API responses (default: false)
- ONTOLOGY_ADVISORY_ENABLED: Enable session-scoped ontology advisory suggestions (default: false)
- ONTOLOGY_AUTO_ANSWER_ENABLED: Enable session-scoped ontology default auto-answers (default: false)
- ONTOLOGY_REASONING_ENABLED: Enable materialized ontology reasoning into INFERRED (default: false)
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

import os
from typing import Any, Mapping, Optional, Tuple


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
        self._use_hypergraph = use_hypergraph if use_hypergraph is not None else self._env_bool("USE_HYPERGRAPH", True)
        self._legacy_iterate = legacy_iterate if legacy_iterate is not None else self._env_bool("LEGACY_ITERATE", True)
        self._layered_memory = layered_memory if layered_memory is not None else self._env_bool("LAYERED_MEMORY", True)
        self._ml_optimized_dfs = ml_optimized_dfs if ml_optimized_dfs is not None else self._env_bool("ML_OPTIMIZED_DFS", False)
        self._async_sync_enabled = async_sync_enabled if async_sync_enabled is not None else self._env_bool("ASYNC_SYNC_ENABLED", False)
        self._modular_imports = modular_imports if modular_imports is not None else self._env_bool("MODULAR_IMPORTS", False)
        self._hybrid_orchestrator = hybrid_orchestrator if hybrid_orchestrator is not None else self._env_bool("HYBRID_ORCHESTRATOR", False)
        self._async_post_reasoning = async_post_reasoning if async_post_reasoning is not None else self._env_bool("ASYNC_POST_REASONING", False)
        self._generate_post_reasoning_ttl = (
            generate_post_reasoning_ttl
            if generate_post_reasoning_ttl is not None
            else self._env_bool("GENERATE_POST_REASONING_TTL", False)
        )
        self._prov_o_trace = prov_o_trace if prov_o_trace is not None else self._env_bool("PROV_O_TRACE", False)
        self._enriched_api = enriched_api if enriched_api is not None else self._env_bool("ENRICHED_API", False)
        self._ontology_advisory_enabled = ontology_advisory_enabled if ontology_advisory_enabled is not None else self._env_bool("ONTOLOGY_ADVISORY_ENABLED", False)
        self._ontology_auto_answer = ontology_auto_answer if ontology_auto_answer is not None else self._env_bool("ONTOLOGY_AUTO_ANSWER_ENABLED", False)
        self._ontology_auto_answer_confidence_threshold = (
            ontology_auto_answer_confidence_threshold
            if ontology_auto_answer_confidence_threshold is not None
            else self._env_float("ONTOLOGY_AUTO_ANSWER_CONFIDENCE_THRESHOLD", 0.85)
        )
        self._ontology_reasoning = (
            ontology_reasoning
            if ontology_reasoning is not None
            else self._env_bool("ONTOLOGY_REASONING_ENABLED", False)
        )
        self._ontology_reasoning_confidence_threshold = (
            ontology_reasoning_confidence_threshold
            if ontology_reasoning_confidence_threshold is not None
            else self._env_float("ONTOLOGY_REASONING_CONFIDENCE_THRESHOLD", 0.85)
        )
        self._ontology_reasoning_min_hierarchy_depth = (
            ontology_reasoning_min_hierarchy_depth
            if ontology_reasoning_min_hierarchy_depth is not None
            else self._env_int("ONTOLOGY_REASONING_MIN_HIERARCHY_DEPTH", 1)
        )
        self._ontology_reasoning_max_closure_depth = (
            ontology_reasoning_max_closure_depth
            if ontology_reasoning_max_closure_depth is not None
            else self._env_int("ONTOLOGY_REASONING_MAX_CLOSURE_DEPTH", 10)
        )
        self._ontology_question_strategy = (
            ontology_question_strategy
            if ontology_question_strategy is not None
            else self._env_bool_any(
                (
                    "ONTOLOGY_QUESTION_STRATEGY_ENABLED",
                    "ONTOLOGY_QUESTION_STRATEGY",
                ),
                False,
            )
        )
        self._redis_session_store = redis_session_store if redis_session_store is not None else self._env_bool("REDIS_SESSION_STORE", False)
        self._llm_enhancements = llm_enhancements if llm_enhancements is not None else self._env_bool("LLM_ENHANCEMENTS", False)
        self._strict_port_contracts = strict_port_contracts if strict_port_contracts is not None else self._env_bool("STRICT_PORT_CONTRACTS", True)
        self._observability_enabled = observability_enabled if observability_enabled is not None else self._env_bool("OBSERVABILITY_ENABLED", False)
        self._auth_enabled = auth_enabled if auth_enabled is not None else self._env_bool("AUTH_ENABLED", False)
        self._abduction_enabled = abduction_enabled if abduction_enabled is not None else self._env_bool("ABDUCTION_ENABLED", False)
        self._induction_pipeline = induction_pipeline if induction_pipeline is not None else self._env_bool("INDUCTION_PIPELINE", False)
        self._reasoning_router = reasoning_router if reasoning_router is not None else self._env_bool("REASONING_ROUTER", True)
        self._confidence_thresholds = confidence_thresholds if confidence_thresholds is not None else self._env_bool("CONFIDENCE_THRESHOLDS", True)
        self._frozen = False

    @staticmethod
    def _env_bool(name: str, default: bool) -> bool:
        """Read a boolean from an environment variable."""
        val = os.environ.get(f"INFERRA_{name}", "").lower()
        if val in ("true", "1", "yes"):
            return True
        if val in ("false", "0", "no"):
            return False
        return default

    @classmethod
    def _env_bool_any(cls, names: Tuple[str, ...], default: bool) -> bool:
        """Read a boolean from the first configured environment variable."""
        for name in names:
            raw = os.environ.get(f"INFERRA_{name}", "")
            if raw:
                return cls._env_bool(name, default)
        return default

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        """Read a float from an environment variable."""
        val = os.environ.get(f"INFERRA_{name}", "")
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _env_int(name: str, default: int) -> int:
        """Read an integer from an environment variable."""
        val = os.environ.get(f"INFERRA_{name}", "")
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

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
            "use_hypergraph": self._use_hypergraph,
            "legacy_iterate": self._legacy_iterate,
            "layered_memory": self._layered_memory,
            "ml_optimized_dfs": self._ml_optimized_dfs,
            "async_sync_enabled": self._async_sync_enabled,
            "modular_imports": self._modular_imports,
            "hybrid_orchestrator": self._hybrid_orchestrator,
            "async_post_reasoning": self._async_post_reasoning,
            "generate_post_reasoning_ttl": self._generate_post_reasoning_ttl,
            "prov_o_trace": self._prov_o_trace,
            "enriched_api": self._enriched_api,
            "ontology_advisory_enabled": self._ontology_advisory_enabled,
            "ontology_auto_answer": self._ontology_auto_answer,
            "ontology_auto_answer_confidence_threshold": self._ontology_auto_answer_confidence_threshold,
            "ontology_reasoning": self._ontology_reasoning,
            "ontology_reasoning_confidence_threshold": self._ontology_reasoning_confidence_threshold,
            "ontology_reasoning_min_hierarchy_depth": self._ontology_reasoning_min_hierarchy_depth,
            "ontology_reasoning_max_closure_depth": self._ontology_reasoning_max_closure_depth,
            "ontology_question_strategy": self._ontology_question_strategy,
            "redis_session_store": self._redis_session_store,
            "llm_enhancements": self._llm_enhancements,
            "strict_port_contracts": self._strict_port_contracts,
            "observability_enabled": self._observability_enabled,
            "auth_enabled": self._auth_enabled,
            "abduction_enabled": self._abduction_enabled,
            "induction_pipeline": self._induction_pipeline,
            "reasoning_router": self._reasoning_router,
            "confidence_thresholds": self._confidence_thresholds,
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
        }


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


# Module-level default flags
_default_flags: FeatureFlags = FeatureFlags()


def get_feature_flags() -> FeatureFlags:
    """Get the global feature flags instance."""
    return _default_flags


def reset_feature_flags(**overrides) -> FeatureFlags:
    """Create fresh feature flags (for testing or new sessions)."""
    return FeatureFlags(**overrides)
