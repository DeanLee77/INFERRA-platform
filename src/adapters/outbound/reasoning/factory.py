import os
from typing import Union

from src.adapters.outbound.llm.real_llm_orchestrator import RealLLMOrchestrator
from src.adapters.outbound.reasoning.celery_induction_adapter import CeleryInductionAdapter
from src.adapters.outbound.reasoning.llm_abduction_adapter import LLMAbductionAdapter
from src.adapters.outbound.reasoning.null_abduction_adapter import NullAbductionAdapter
from src.adapters.outbound.reasoning.null_induction_adapter import NullInductionAdapter
from src.adapters.outbound.reasoning.z3_abduction_adapter import Z3AbductionAdapter
from src.domain.reasoning.null_router import NullReasoningRouter
from src.domain.reasoning.reasoning_router import ReasoningRouter
from src.domain.state.feature_flags import FeatureFlags
from src.ports.abduction_port import AbductionPort
from src.ports.induction_port import InductionPort


def create_abduction_adapter(flags: FeatureFlags) -> AbductionPort:
    if flags.abduction_enabled:
        provider = os.environ.get("INFERRA_ABDUCTION_ADAPTER", "z3").strip().lower()
        if provider == "llm" and flags.llm_enhancements:
            return LLMAbductionAdapter(RealLLMOrchestrator())
        return Z3AbductionAdapter()
    return NullAbductionAdapter()


def create_induction_adapter(flags: FeatureFlags) -> InductionPort:
    if flags.induction_pipeline:
        return CeleryInductionAdapter()
    return NullInductionAdapter()


def create_reasoning_router(
    flags: FeatureFlags,
) -> Union[ReasoningRouter, NullReasoningRouter]:
    """Build the router selected by one frozen feature-flag snapshot."""
    if not flags.reasoning_router:
        return NullReasoningRouter()
    return ReasoningRouter(
        abduction=create_abduction_adapter(flags),
        induction=create_induction_adapter(flags),
        abduction_enabled=flags.abduction_enabled,
        induction_pipeline=flags.induction_pipeline,
        confidence_thresholds=flags.confidence_thresholds,
    )
