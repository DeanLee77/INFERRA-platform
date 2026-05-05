import pytest

from src.domain.fact_values import FactValue
from src.domain.inference.backward_chain_orchestrator import BackwardChainOrchestrator
from src.domain.inference.inference_engine import InferenceEngine
from src.domain.reasoning import Hypothesis, ReasoningRouter
from src.domain.session import InferenceContext, SessionManager
from src.domain.state import FactSource, LayeredFactStore
from src.adapters.outbound.reasoning.mock_abduction_adapter import MockAbductionAdapter


def _manager_with_goal():
    store = LayeredFactStore()
    store.set_fact("goal", FactValue(True), FactSource.INFERRED)
    ctx = InferenceContext(
        session_id="s1",
        rule_name="rule",
        target="goal",
        mandatory=[],
        fact_store=store,
    )
    manager = SessionManager()
    manager.create_snapshot("s1", ctx)
    return manager


@pytest.mark.asyncio
async def test_orchestrator_returns_converged_result():
    orchestrator = BackwardChainOrchestrator(InferenceEngine(), _manager_with_goal())

    result = await orchestrator.run_convergence_loop("s1")

    assert result.converged is True
    assert result.reason == "GOAL_REACHED"
    assert result.strategy_used == "ConservativeQuestionStrategy"


@pytest.mark.asyncio
async def test_orchestrator_returns_iteration_cap_when_pending():
    manager = SessionManager()
    store = LayeredFactStore()
    ctx = InferenceContext(
        session_id="s1",
        rule_name="rule",
        target="goal",
        mandatory=[],
        fact_store=store,
    )
    manager.create_snapshot("s1", ctx)
    orchestrator = BackwardChainOrchestrator(InferenceEngine(), manager)

    result = await orchestrator.run_convergence_loop("s1", max_iterations=2)

    assert result.converged is False
    assert result.reason == "ITERATION_CAP"
    assert result.iteration == 2


@pytest.mark.asyncio
async def test_orchestrator_injects_abduction_hypothesis_under_lock():
    manager = SessionManager()
    store = LayeredFactStore()
    ctx = InferenceContext(
        session_id="s1",
        rule_name="rule",
        target="goal",
        mandatory=[],
        fact_store=store,
    )
    manager.create_snapshot("s1", ctx)
    router = ReasoningRouter(
        MockAbductionAdapter([Hypothesis("goal", "true", 0.91)]),
        abduction_enabled=True,
    )
    orchestrator = BackwardChainOrchestrator(
        InferenceEngine(),
        manager,
        reasoning_router=router,
    )

    result = await orchestrator.run_convergence_loop("s1", max_iterations=2)

    assert result.converged is True
    assert result.reason == "GOAL_REACHED"
    assert store.peek_in_layer("goal", FactSource.HYPOTHETICAL).get_value() is True
    assert ctx.abduction_attempted is True
    assert "ABDUCTION_INJECTED" in result.convergence_trace
