import json
from unittest.mock import MagicMock, patch

from src.adapters.outbound.reasoning.factory import create_abduction_adapter
from src.adapters.outbound.reasoning.llm_abduction_adapter import LLMAbductionAdapter
from src.adapters.outbound.reasoning.z3_abduction_adapter import Z3AbductionAdapter
from src.domain.state.feature_flags import FeatureFlags
from src.ports.abduction_port import AbductionPort


class _MockLLM:
    def __init__(self, response: str = "") -> None:
        self.response = response
        self.calls = []

    def chat(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        self.calls.append((system_prompt, user_prompt, kwargs))
        return self.response


class _LegacyChatLLM:
    def __init__(self, response: str) -> None:
        self.response = response

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        return self.response


def test_llm_abduction_adapter_returns_empty_without_chat_capable_llm():
    adapter = LLMAbductionAdapter(llm_orchestrator=object())

    assert isinstance(adapter, AbductionPort)
    assert adapter.propose_hypotheses("eligible", {}, {}) == []


def test_llm_abduction_adapter_parses_and_sorts_json_hypotheses():
    llm = _MockLLM(json.dumps([
        {"fact_name": "b", "suggested_value": "false", "confidence": 0.4},
        {"fact_name": "a", "suggested_value": "true", "confidence": 0.9},
    ]))
    adapter = LLMAbductionAdapter(llm_orchestrator=llm)

    result = adapter.propose_hypotheses("eligible", {}, {})

    assert result[0]["fact_name"] == "a"
    assert result[0]["suggested_value"] == "true"
    assert result[0]["dependency_path"] == ["eligible", "a"]
    assert result[1]["fact_name"] == "b"
    assert llm.calls[0][2]["operation"] == "abduction"


def test_llm_abduction_adapter_accepts_legacy_chat_signature_and_object_json():
    llm = _LegacyChatLLM(json.dumps({"fact_name": "x", "confidence": "bad"}))
    adapter = LLMAbductionAdapter(llm_orchestrator=llm)

    result = adapter.propose_hypotheses("eligible", {}, {})

    assert result == [
        {
            "fact_name": "x",
            "suggested_value": "true",
            "confidence": 0.5,
            "dependency_path": ["eligible", "x"],
            "ontology_consistent": True,
        }
    ]


def test_llm_abduction_adapter_extracts_json_from_markdown_and_clamps_confidence():
    response = 'Here: [{"fact_name": "x", "confidence": 2}, {"fact_name": "y", "confidence": -1}]'
    adapter = LLMAbductionAdapter(llm_orchestrator=_MockLLM(response), max_hypotheses=2)

    result = adapter.propose_hypotheses("eligible", {}, {})

    assert result[0]["confidence"] == 1.0
    assert result[1]["confidence"] == 0.0


def test_llm_abduction_adapter_filters_to_dependency_leaf_candidates():
    response = json.dumps([
        {"fact_name": "hallucinated", "confidence": 0.99},
        {"fact_name": "missing", "confidence": 0.7},
    ])
    snapshot = {"child_groups": {"goal": ((1, ("known", "missing")),)}}
    adapter = LLMAbductionAdapter(llm_orchestrator=_MockLLM(response))

    result = adapter.propose_hypotheses("goal", {"known": True}, snapshot)

    assert [item["fact_name"] for item in result] == ["missing"]


def test_llm_abduction_adapter_returns_empty_on_call_error_or_parse_failure():
    failing = MagicMock()
    failing.chat.side_effect = RuntimeError("provider down")

    assert LLMAbductionAdapter(failing).propose_hypotheses("goal", {}, {}) == []
    assert LLMAbductionAdapter(_MockLLM("not json")).propose_hypotheses("goal", {}, {}) == []


def test_llm_abduction_adapter_returns_empty_when_prompt_sanitizer_rejects():
    sanitizer = MagicMock()
    sanitizer.sanitize.side_effect = ValueError("rejected")
    adapter = LLMAbductionAdapter(_MockLLM("[]"), prompt_sanitizer=sanitizer)

    assert adapter.propose_hypotheses("goal", {}, {}) == []


def test_llm_abduction_factory_defaults_to_z3_and_can_select_llm():
    assert isinstance(create_abduction_adapter(FeatureFlags(abduction_enabled=True)), Z3AbductionAdapter)

    with patch.dict("os.environ", {"INFERRA_ABDUCTION_ADAPTER": "llm"}):
        with patch("src.adapters.outbound.reasoning.factory.RealLLMOrchestrator", return_value=_MockLLM("[]")):
            adapter = create_abduction_adapter(
                FeatureFlags(abduction_enabled=True, llm_enhancements=True)
            )

    assert isinstance(adapter, LLMAbductionAdapter)

