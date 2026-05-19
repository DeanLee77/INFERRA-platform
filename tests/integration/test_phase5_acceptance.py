from unittest.mock import MagicMock, patch

import pytest

from src.adapters.outbound.reasoning.celery_induction_adapter import CeleryInductionAdapter
from src.adapters.outbound.reasoning.mock_abduction_adapter import MockAbductionAdapter
from src.adapters.outbound.reasoning.mock_induction_adapter import MockInductionAdapter
from src.adapters.outbound.reasoning.null_abduction_adapter import NullAbductionAdapter
from src.adapters.outbound.reasoning.null_induction_adapter import NullInductionAdapter
from src.adapters.outbound.reasoning.z3_abduction_adapter import Z3AbductionAdapter
from src.domain.fact_values import FactValue
from src.domain.graph.dependency_type import DependencyType
from src.domain.reasoning import Hypothesis, ReasoningRouter
from src.domain.session import InferenceContext
from src.domain.state import FactSource, LayeredFactStore
from src.domain.state.session_schema import migrate_session
from src.ports.abduction_port import AbductionPort
from src.ports.induction_port import InductionPort
from src.services.rule_sandbox import RuleSandbox
from src.tasks.induction import InductionCircuitBreaker


def test_phase5_acceptance_ports_and_adapters_are_contract_compliant():
    abduction_adapters = [
        NullAbductionAdapter(),
        MockAbductionAdapter([Hypothesis("missing", "true", 0.8)]),
        Z3AbductionAdapter(timeout_ms=200, max_models=5),
    ]
    induction_adapters = [
        NullInductionAdapter(),
        MockInductionAdapter(["INPUT trace_pattern AS BOOLEAN\nlearned IS TRUE IF trace_pattern"]),
        CeleryInductionAdapter(),
    ]

    assert all(isinstance(adapter, AbductionPort) for adapter in abduction_adapters)
    assert all(isinstance(adapter, InductionPort) for adapter in induction_adapters)


def test_phase5_acceptance_z3_abduction_is_bounded_and_read_only():
    adapter = Z3AbductionAdapter(timeout_ms=200, max_models=1)
    working_memory = {"known": True}
    graph_snapshot = {
        "child_groups": {
            "goal": ((int(DependencyType.AND), ("known", "missing")),),
        }
    }

    hypotheses = adapter.propose_hypotheses("goal", working_memory, graph_snapshot)

    assert len(hypotheses) == 1
    assert hypotheses[0]["fact_name"] == "missing"
    assert hypotheses[0]["confidence"] >= 0.5
    assert working_memory == {"known": True}


def test_phase5_acceptance_fact_layers_and_schema_migration():
    store = LayeredFactStore()
    store.set_fact("decision", FactValue("semantic"), FactSource.SEMANTIC)
    store.set_fact("decision", FactValue("hypothesis"), FactSource.HYPOTHETICAL)
    store.set_fact("decision", FactValue("learned"), FactSource.LEARNED)
    store.set_fact("decision", FactValue("inferred"), FactSource.INFERRED)
    store.set_fact("decision", FactValue("asserted"), FactSource.ASSERTED)

    assert store.get_unified_view()["decision"].get_value() == "asserted"
    assert "decision" in store.get_overrides()
    store.invalidate_hypotheses()
    assert FactSource.HYPOTHETICAL not in store.get_fact_sources("decision")

    migrated = migrate_session({"id": "phase4", "metadata": {"schema_version": 4}}, from_version=4)
    assert migrated["reasoning_mode"] == "DEDUCTION"
    assert migrated["confidence"] == 1.0
    assert migrated["hypothesis_trace"] == []
    assert migrated["induction_job_id"] is None
    assert migrated["abduction_attempted"] is False
    assert migrated["abduction_count"] == 0

    future = migrate_session(
        {
            "id": "future",
            "metadata": {"schema_version": 4},
            "fact_sources": {"future_fact": "FUTURE_SOURCE"},
        },
        from_version=4,
    )
    assert future["fact_sources"]["future_fact"] == FactSource.INFERRED.value


def test_phase5_acceptance_router_threshold_precedence_and_induction_fallback():
    router = ReasoningRouter(
        MockAbductionAdapter([Hypothesis("maybe", "true", 0.7)]),
        MockInductionAdapter(),
        abduction_enabled=True,
        induction_pipeline=True,
        min_confidence=0.5,
        rule_confidence_thresholds={"strict_rule": 0.8},
    )

    blocked_by_rule = router.route(
        session_id="s1",
        target="goal",
        working_memory={},
        graph_snapshot={},
        iteration_count=2,
        has_unasked_questions=False,
        rule_name="strict_rule",
        trace_backlog_size=5,
    )
    allowed_by_session = router.route(
        session_id="s1",
        target="goal",
        working_memory={},
        graph_snapshot={},
        iteration_count=2,
        has_unasked_questions=False,
        rule_name="strict_rule",
        session_min_confidence=0.65,
    )

    assert blocked_by_rule.mode == "INDUCTION"
    assert blocked_by_rule.induction_job_id == "mock-induction-1"
    assert allowed_by_session.mode == "ABDUCTION"


def test_phase5_acceptance_context_records_mode_switches():
    ctx = InferenceContext(
        session_id="s1",
        rule_name="rule",
        target="goal",
        mandatory=[],
        fact_store=LayeredFactStore(),
    )

    ctx.record_abduction_attempt([{"fact_name": "missing", "confidence": 0.82}])
    assert ctx.reasoning_mode == "ABDUCTION"
    assert ctx.abduction_attempted is True
    assert ctx.abduction_count == 1
    assert ctx.confidence == 0.82

    ctx.set_induction_job("job-1")
    assert ctx.reasoning_mode == "INDUCTION"
    assert ctx.induction_job_id == "job-1"
    assert ctx.confidence == 0.5


def test_phase5_acceptance_induction_idempotency_and_circuit_breaker():
    CeleryInductionAdapter.clear_idempotency_cache()
    adapter = CeleryInductionAdapter()
    with patch("src.tasks.induction.run_induction_batch") as task:
        task.delay.return_value = MagicMock(id="job-1")
        first = adapter.start_batch(["s2", "s1"], "rule")
        second = adapter.start_batch(["s1", "s2"], "rule")

    assert first == second
    task.delay.assert_called_once()

    breaker = InductionCircuitBreaker(failure_threshold=1, recovery_timeout=30)
    breaker.record_failure()
    with pytest.raises(Exception, match="Induction circuit is open"):
        breaker.before_call()


def test_phase5_acceptance_rule_sandbox_blocks_invalid_promotion():
    valid = "INPUT trace_pattern AS BOOLEAN\nlearned_fact IS TRUE IF trace_pattern"
    invalid = "learned_fact IS TRUE IF missing_declaration"
    sandbox = RuleSandbox()

    valid_result = sandbox.promote_candidate("job-1", valid, [valid], "learned_rule")
    invalid_result = sandbox.promote_candidate("job-1", invalid, [invalid], "learned_rule")

    assert valid_result.status == "promoted"
    assert invalid_result.status == "rejected"
    assert invalid_result.errors
