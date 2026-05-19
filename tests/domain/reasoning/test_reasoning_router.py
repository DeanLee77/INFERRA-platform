from src.adapters.outbound.reasoning.mock_abduction_adapter import MockAbductionAdapter
from src.adapters.outbound.reasoning.mock_induction_adapter import MockInductionAdapter
from src.adapters.outbound.reasoning.null_abduction_adapter import NullAbductionAdapter
from src.domain.reasoning import Hypothesis, NullReasoningRouter, ReasoningRouter


def test_router_keeps_deduction_when_questions_remain():
    router = ReasoningRouter(
        MockAbductionAdapter(),
        abduction_enabled=True,
    )

    decision = router.route(
        session_id="s1",
        target="goal",
        working_memory={},
        graph_snapshot={},
        iteration_count=5,
        has_unasked_questions=True,
    )

    assert decision.mode == "DEDUCTION"
    assert decision.action == "CONTINUE_LOOP"
    assert decision.reason == "unasked_questions"


def test_router_waits_for_deduction_warmup():
    router = ReasoningRouter(
        MockAbductionAdapter(),
        abduction_enabled=True,
    )

    decision = router.route(
        session_id="s1",
        target="goal",
        working_memory={},
        graph_snapshot={},
        iteration_count=1,
        has_unasked_questions=False,
    )

    assert decision.mode == "DEDUCTION"
    assert decision.reason == "deduction_warmup"


def test_router_selects_high_confidence_abduction_after_stall():
    router = ReasoningRouter(
        MockAbductionAdapter(
            [
                Hypothesis("low", "true", 0.2),
                Hypothesis("best", "true", 0.9),
                Hypothesis("bad_ontology", "true", 0.99, ontology_consistent=False),
            ]
        ),
        abduction_enabled=True,
        min_confidence=0.5,
    )

    decision = router.route(
        session_id="s1",
        target="goal",
        working_memory={},
        graph_snapshot={},
        iteration_count=2,
        has_unasked_questions=False,
    )

    assert decision.mode == "ABDUCTION"
    assert decision.action == "INJECT_HYPOTHESIS"
    assert decision.hypotheses[0]["fact_name"] == "best"
    assert decision.confidence == 0.9


def test_router_can_start_induction_when_enabled_and_trace_backlog_exists():
    router = ReasoningRouter(
        NullAbductionAdapter(),
        MockInductionAdapter(),
        abduction_enabled=False,
        induction_pipeline=True,
    )

    decision = router.route(
        session_id="s1",
        target="goal",
        working_memory={},
        graph_snapshot={},
        iteration_count=2,
        has_unasked_questions=False,
        trace_backlog_size=10,
        rule_name="rule",
    )

    assert decision.mode == "INDUCTION"
    assert decision.action == "START_BATCH"
    assert decision.induction_job_id == "mock-induction-1"


def test_null_router_always_keeps_deduction():
    decision = NullReasoningRouter().route(
        session_id="s1",
        target="goal",
        working_memory={},
        graph_snapshot={},
        iteration_count=5,
        has_unasked_questions=False,
    )

    assert decision.mode == "DEDUCTION"
    assert decision.reason == "router_disabled"


def test_router_uses_env_confidence_threshold(monkeypatch):
    monkeypatch.setenv("INFERRA_CONFIDENCE_THRESHOLD", "0.95")
    router = ReasoningRouter(
        MockAbductionAdapter([Hypothesis("maybe", "true", 0.9)]),
        abduction_enabled=True,
    )

    decision = router.route(
        session_id="s1",
        target="goal",
        working_memory={},
        graph_snapshot={},
        iteration_count=2,
        has_unasked_questions=False,
    )

    assert router.min_confidence == 0.95
    assert decision.mode == "DEDUCTION"
    assert decision.reason == "no_alternate_route"


def test_router_confidence_threshold_precedence_session_rule_global():
    router = ReasoningRouter(
        MockAbductionAdapter([Hypothesis("maybe", "true", 0.7)]),
        abduction_enabled=True,
        min_confidence=0.5,
        rule_confidence_thresholds={"strict_rule": 0.8},
    )

    rule_decision = router.route(
        session_id="s1",
        target="goal",
        working_memory={},
        graph_snapshot={},
        iteration_count=2,
        has_unasked_questions=False,
        rule_name="strict_rule",
    )
    session_decision = router.route(
        session_id="s1",
        target="goal",
        working_memory={},
        graph_snapshot={},
        iteration_count=2,
        has_unasked_questions=False,
        rule_name="strict_rule",
        session_min_confidence=0.65,
    )
    explicit_rule_decision = router.route(
        session_id="s1",
        target="goal",
        working_memory={},
        graph_snapshot={},
        iteration_count=2,
        has_unasked_questions=False,
        rule_min_confidence=0.75,
    )

    assert rule_decision.mode == "DEDUCTION"
    assert session_decision.mode == "ABDUCTION"
    assert explicit_rule_decision.mode == "DEDUCTION"
