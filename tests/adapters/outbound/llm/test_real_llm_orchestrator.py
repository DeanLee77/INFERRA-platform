from unittest.mock import MagicMock

from src.adapters.outbound.llm.real_llm_orchestrator import RealLLMOrchestrator
from src.ports.llm_orchestrator_port import LLMOrchestratorPort


def _client(content: str):
    llm = MagicMock()
    llm.client = MagicMock()
    llm.model = "model"
    llm.timeout = 3
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    llm.client.chat.completions.create.return_value = response
    return llm


def test_real_llm_orchestrator_falls_back_when_not_configured():
    llm = MagicMock()
    llm.client = None
    llm.model = None
    orchestrator = RealLLMOrchestrator(llm)

    result = orchestrator.map_nl_to_goal("can I claim?", "rule")

    assert isinstance(orchestrator, LLMOrchestratorPort)
    assert result["fallback"] is True
    assert orchestrator.enhance_question_prompt("node", "age") == "age"
    assert orchestrator.generate_explanation("trace") == "trace"


def test_real_llm_orchestrator_maps_goal_from_json():
    orchestrator = RealLLMOrchestrator(
        _client('{"node_name":"goal","confidence":0.88,"fallback":false,"message":""}')
    )

    result = orchestrator.map_nl_to_goal("can I claim?", "rule")

    assert result["node_name"] == "goal"
    assert result["confidence"] == 0.88
    assert result["prompt_version"] == "llm-orchestrator-v1"


def test_real_llm_orchestrator_goal_mapping_falls_back_on_bad_json():
    orchestrator = RealLLMOrchestrator(_client("not json"))

    result = orchestrator.map_nl_to_goal("can I claim?", "rule")

    assert result["fallback"] is True
    assert result["message"] == "LLM goal mapping failed"


def test_real_llm_orchestrator_enhances_prompt():
    orchestrator = RealLLMOrchestrator(_client("What is your age?"))

    assert orchestrator.enhance_question_prompt("node", "age") == "What is your age?"


def test_real_llm_orchestrator_enhance_prompt_falls_back_on_empty_or_error():
    orchestrator = RealLLMOrchestrator(_client(""))
    assert orchestrator.enhance_question_prompt("node", "age") == "age"

    failing = RealLLMOrchestrator(_client("ignored"))
    failing._llm.client.chat.completions.create.side_effect = Exception("llm down")
    assert failing.enhance_question_prompt("node", "age") == "age"


def test_real_llm_orchestrator_generates_explanation_and_falls_back():
    orchestrator = RealLLMOrchestrator(_client("Plain explanation"))
    assert orchestrator.generate_explanation("trace", "turtle", "s1") == "Plain explanation"

    empty = RealLLMOrchestrator(_client(""))
    assert empty.generate_explanation("trace") == "trace"

    failing = RealLLMOrchestrator(_client("ignored"))
    failing._llm.client.chat.completions.create.side_effect = Exception("llm down")
    assert failing.generate_explanation("trace") == "trace"
