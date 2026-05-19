from unittest.mock import MagicMock

import pytest

from src.adapters.outbound.llm.real_llm_orchestrator import (
    LLMCircuitBreaker,
    RealLLMOrchestrator,
    reset_default_llm_circuit,
)
from src.ports.llm_orchestrator_port import LLMOrchestratorPort


@pytest.fixture(autouse=True)
def reset_circuit():
    reset_default_llm_circuit()
    yield
    reset_default_llm_circuit()


def _response(content: str):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response


def _client(content: str):
    llm = MagicMock()
    llm.client = MagicMock()
    llm.model = "model"
    llm.timeout = 3
    llm.client.chat.completions.create.return_value = _response(content)
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


def test_real_llm_orchestrator_chat_uses_guarded_completion():
    orchestrator = RealLLMOrchestrator(_client("chat response"))

    assert orchestrator.chat("system", "user", operation="abduction") == "chat response"


def test_real_llm_orchestrator_retries_transient_provider_errors():
    llm = _client("ignored")
    llm.client.chat.completions.create.side_effect = [
        RuntimeError("rate limited"),
        _response('{"node_name":"goal","confidence":0.91,"fallback":false,"message":""}'),
    ]
    breaker = LLMCircuitBreaker(failure_threshold=3, recovery_timeout=30)
    orchestrator = RealLLMOrchestrator(
        llm,
        max_retries=1,
        retry_backoff_seconds=0,
        circuit_breaker=breaker,
    )

    result = orchestrator.map_nl_to_goal("can I claim?", "rule")

    assert result["fallback"] is False
    assert result["node_name"] == "goal"
    assert llm.client.chat.completions.create.call_count == 2
    assert breaker.state == "closed"


def test_real_llm_orchestrator_opens_circuit_after_failures():
    llm = _client("ignored")
    llm.client.chat.completions.create.side_effect = RuntimeError("provider down")
    breaker = LLMCircuitBreaker(failure_threshold=1, recovery_timeout=30)
    orchestrator = RealLLMOrchestrator(
        llm,
        max_retries=0,
        retry_backoff_seconds=0,
        circuit_breaker=breaker,
    )

    first = orchestrator.map_nl_to_goal("can I claim?", "rule")
    second = orchestrator.map_nl_to_goal("can I claim?", "rule")

    assert first["fallback"] is True
    assert second["fallback"] is True
    assert breaker.state == "open"
    assert llm.client.chat.completions.create.call_count == 1


def test_real_llm_orchestrator_allows_half_open_recovery():
    now = [0.0]
    breaker = LLMCircuitBreaker(
        failure_threshold=1,
        recovery_timeout=10,
        clock=lambda: now[0],
    )
    llm = _client("ignored")
    llm.client.chat.completions.create.side_effect = [
        RuntimeError("provider down"),
        _response('{"node_name":"goal","confidence":0.93,"fallback":false,"message":""}'),
    ]
    orchestrator = RealLLMOrchestrator(
        llm,
        max_retries=0,
        retry_backoff_seconds=0,
        circuit_breaker=breaker,
    )

    fallback = orchestrator.map_nl_to_goal("can I claim?", "rule")
    now[0] = 11.0
    recovered = orchestrator.map_nl_to_goal("can I claim?", "rule")

    assert fallback["fallback"] is True
    assert recovered["fallback"] is False
    assert breaker.state == "closed"
    assert llm.client.chat.completions.create.call_count == 2
