import os

from src.adapters.outbound.llm.real_llm_orchestrator import RealLLMOrchestrator
from src.adapters.outbound.reasoning.celery_induction_adapter import CeleryInductionAdapter
from src.adapters.outbound.reasoning.llm_abduction_adapter import LLMAbductionAdapter
from src.adapters.outbound.reasoning.null_abduction_adapter import NullAbductionAdapter
from src.adapters.outbound.reasoning.null_induction_adapter import NullInductionAdapter
from src.adapters.outbound.reasoning.z3_abduction_adapter import Z3AbductionAdapter
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
