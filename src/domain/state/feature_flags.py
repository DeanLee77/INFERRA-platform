"""
Feature flag configuration for INFERRA.

Phase 1 feature flags:
- USE_HYPERGRAPH: Use HyperAdjacencyGraph instead of DependencyMatrix (default: false)
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
from typing import Optional


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
        prov_o_trace: Optional[bool] = None,
        enriched_api: Optional[bool] = None,
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
        self._use_hypergraph = use_hypergraph if use_hypergraph is not None else self._env_bool("USE_HYPERGRAPH", False)
        self._legacy_iterate = legacy_iterate if legacy_iterate is not None else self._env_bool("LEGACY_ITERATE", True)
        self._layered_memory = layered_memory if layered_memory is not None else self._env_bool("LAYERED_MEMORY", True)
        self._ml_optimized_dfs = ml_optimized_dfs if ml_optimized_dfs is not None else self._env_bool("ML_OPTIMIZED_DFS", False)
        self._async_sync_enabled = async_sync_enabled if async_sync_enabled is not None else self._env_bool("ASYNC_SYNC_ENABLED", False)
        self._modular_imports = modular_imports if modular_imports is not None else self._env_bool("MODULAR_IMPORTS", False)
        self._hybrid_orchestrator = hybrid_orchestrator if hybrid_orchestrator is not None else self._env_bool("HYBRID_ORCHESTRATOR", False)
        self._async_post_reasoning = async_post_reasoning if async_post_reasoning is not None else self._env_bool("ASYNC_POST_REASONING", False)
        self._prov_o_trace = prov_o_trace if prov_o_trace is not None else self._env_bool("PROV_O_TRACE", False)
        self._enriched_api = enriched_api if enriched_api is not None else self._env_bool("ENRICHED_API", False)
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
    def prov_o_trace(self) -> bool:
        return self._prov_o_trace

    @property
    def enriched_api(self) -> bool:
        return self._enriched_api

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
            "prov_o_trace": self._prov_o_trace,
            "enriched_api": self._enriched_api,
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


# Module-level default flags
_default_flags: FeatureFlags = FeatureFlags()


def get_feature_flags() -> FeatureFlags:
    """Get the global feature flags instance."""
    return _default_flags


def reset_feature_flags(**overrides) -> FeatureFlags:
    """Create fresh feature flags (for testing or new sessions)."""
    return FeatureFlags(**overrides)
