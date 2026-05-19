from unittest.mock import MagicMock

from src.adapters.outbound.llm.llm_cost_tracker import LLMCostTracker, llm_cost_tracker
from src.adapters.outbound.llm.llm_metrics import LLMMetricsCollector, llm_metrics
from src.adapters.outbound.llm.llm_tracing import LLMTracer, _sanitize_pii, llm_tracer
from src.adapters.outbound.llm.real_llm_orchestrator import RealLLMOrchestrator


def _response(content: str, prompt_tokens: int = 10, completion_tokens: int = 5):
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    return response


def _client(response):
    llm = MagicMock()
    llm.client = MagicMock()
    llm.model = "gpt-3.5-turbo"
    llm.timeout = 3
    llm.client.chat.completions.create.return_value = response
    return llm


def test_llm_cost_tracker_records_by_model():
    tracker = LLMCostTracker()

    cost = tracker.record("gpt-3.5-turbo", 1000, 1000)
    summary = tracker.get_cost_summary()

    assert cost > 0
    assert summary["by_model"]["gpt-3.5-turbo"]["request_count"] == 1
    assert summary["total_cost_usd"] == round(cost, 6)


def test_llm_metrics_collector_summarizes_requests():
    collector = LLMMetricsCollector()

    collector.record(
        operation="goal_mapping",
        model="model",
        provider="provider",
        status="success",
        latency_ms=12.5,
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.001,
    )

    summary = collector.get_summary()
    assert summary["total_requests"] == 1
    assert summary["by_operation"] == {"goal_mapping": 1}
    assert summary["by_status"] == {"success": 1}


def test_llm_tracer_sanitizes_pii():
    tracer = LLMTracer()

    tracer.record(
        trace_id="trace-1",
        operation="goal_mapping",
        model="model",
        provider="provider",
        prompt="Email me at person@example.com",
        response="Call 555-123-4567",
        latency_ms=1.0,
    )

    trace = tracer.get_traces()[0]
    assert "person@example.com" not in trace["prompt"]
    assert "555-123-4567" not in trace["response"]
    assert _sanitize_pii("4111 1111 1111 1111") == "[REDACTED]"


def test_real_llm_orchestrator_records_cost_metrics_and_trace():
    llm_cost_tracker.reset()
    llm_metrics.clear()
    llm_tracer.clear()
    orchestrator = RealLLMOrchestrator(
        _client(_response('{"node_name":"goal","confidence":0.9,"fallback":false,"message":""}'))
    )

    result = orchestrator.map_nl_to_goal("contact me at person@example.com", "rule")

    assert result["node_name"] == "goal"
    assert llm_cost_tracker.get_cost_summary()["by_model"]["gpt-3.5-turbo"]["request_count"] == 1
    assert llm_metrics.get_summary()["by_operation"]["goal_mapping"] == 1
    traces = llm_tracer.get_traces("goal_mapping")
    assert len(traces) == 1
    assert "person@example.com" not in traces[0]["prompt"]
