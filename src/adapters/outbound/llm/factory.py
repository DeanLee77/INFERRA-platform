from src.adapters.outbound.llm.null_llm_orchestrator import NullLLMOrchestrator
from src.adapters.outbound.llm.real_llm_orchestrator import RealLLMOrchestrator
from src.domain.state.feature_flags import FeatureFlags
from src.ports.llm_orchestrator_port import LLMOrchestratorPort


def create_llm_orchestrator(flags: FeatureFlags) -> LLMOrchestratorPort:
    if flags.llm_enhancements:
        return RealLLMOrchestrator()
    return NullLLMOrchestrator()
