import pytest

from src.adapters.outbound.reasoning.z3_abduction_adapter import Z3AbductionAdapter
from src.domain.fact_values import FactValue
from src.domain.graph.dependency_type import DependencyType
from src.domain.inference.backward_chain_orchestrator import BackwardChainOrchestrator
from src.domain.inference.inference_engine import InferenceEngine
from src.domain.reasoning.reasoning_router import ReasoningRouter
from src.domain.session import InferenceContext, SessionManager
from src.domain.state import FactSource, LayeredFactStore
from src.tasks.celery_app import app as celery_app
from src.tasks.induction import run_induction_batch


@pytest.mark.asyncio
async def test_deduction_stall_to_z3_abduction_hypothesis_injection():
    store = LayeredFactStore()
    manager = SessionManager()
    ctx = InferenceContext(
        session_id="tri-modal-s1",
        rule_name="rule",
        target="goal",
        mandatory=[],
        fact_store=store,
    )
    manager.create_snapshot(ctx.session_id, ctx)
    engine = InferenceEngine()
    router = ReasoningRouter(
        Z3AbductionAdapter(timeout_ms=200),
        abduction_enabled=True,
    )
    orchestrator = BackwardChainOrchestrator(
        engine,
        manager,
        reasoning_router=router,
    )

    # No graph on the engine in this focused E2E, so inject the graph snapshot
    # through a tiny router wrapper to test the live Z3 adapter path.
    original_route = router.route

    def route_with_graph(**kwargs):
        kwargs["graph_snapshot"] = {
            "child_groups": {
                "goal": ((int(DependencyType.AND), ("missing_fact",)),)
            }
        }
        return original_route(**kwargs)

    router.route = route_with_graph

    result = await orchestrator.run_convergence_loop(ctx.session_id, max_iterations=2)

    assert result.converged is False
    assert result.reason == "ITERATION_CAP"
    assert store.peek_in_layer("goal", FactSource.HYPOTHETICAL) is None
    assert store.peek_in_layer("missing_fact", FactSource.HYPOTHETICAL).get_value() is True
    assert ctx.abduction_attempted is True


def test_induction_task_eager_generates_candidate_rule():
    previous = celery_app.conf.task_always_eager
    celery_app.conf.task_always_eager = True
    try:
        result = run_induction_batch.delay(["s1", "s2"], "rule")
    finally:
        celery_app.conf.task_always_eager = previous

    assert result.result["status"] == "completed"
    assert result.result["candidate_rules"]
    assert "learned" in result.result["candidate_rules"][0]
