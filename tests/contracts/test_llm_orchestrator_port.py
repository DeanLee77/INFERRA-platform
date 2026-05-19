from src.adapters.outbound.llm.mock_llm_orchestrator import MockLLMOrchestrator
from src.adapters.outbound.llm.null_llm_orchestrator import NullLLMOrchestrator
from src.ports.llm_orchestrator_port import LLMOrchestratorPort


def test_null_llm_orchestrator_implements_port():
    orchestrator = NullLLMOrchestrator()

    assert isinstance(orchestrator, LLMOrchestratorPort)
    assert orchestrator.map_nl_to_goal("can I claim?", "rule")["fallback"] is True


def test_mock_llm_orchestrator_contract():
    orchestrator = MockLLMOrchestrator()

    assert isinstance(orchestrator, LLMOrchestratorPort)
    assert orchestrator.map_nl_to_goal("query", "rule")["confidence"] == 0.95
    assert orchestrator.enhance_question_prompt("node", "age", {}) == "Please provide age"
    assert orchestrator.generate_explanation("trace", session_id="s1") == "Mock explanation"
