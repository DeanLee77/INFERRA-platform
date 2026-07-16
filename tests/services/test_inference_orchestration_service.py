from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.inference.session import InferenceSession
from src.domain.session.inference_context import InferenceContext
from src.domain.session.session_manager import ConvergenceResult
from src.domain.state.feature_flags import FeatureFlags
from src.services.inference_orchestration_service import (
    InferenceOrchestrationService,
    get_inference_orchestration_service,
)


@pytest.mark.asyncio
async def test_stalled_session_uses_frozen_flags_for_router_and_orchestrator():
    flags = FeatureFlags(
        hybrid_orchestrator=True,
        reasoning_router=True,
        abduction_enabled=True,
        confidence_thresholds=False,
    )
    flags.freeze()
    context = InferenceContext(
        session_id="session-1",
        rule_name="rule",
        target="goal",
        mandatory=[],
        fact_store=MagicMock(),
    )
    session = InferenceSession(
        session_id="session-1",
        rule_name="rule",
        target_node_name="goal",
        inference_engine=MagicMock(),
        assessment=MagicMock(),
        feature_flags=flags,
        context=context,
    )
    manager = MagicMock()
    router = MagicMock()
    result = ConvergenceResult(
        converged=False,
        reason="ITERATION_CAP",
        iteration=3,
        working_memory_hash="hash",
        ontology_delta=0,
        session_id=session.session_id,
        convergence_trace=["PENDING", "ITERATION_CAP"],
    )
    orchestrator = MagicMock()
    orchestrator.run_convergence_loop = AsyncMock(return_value=result)

    with patch(
        "src.services.inference_orchestration_service.create_reasoning_router",
        return_value=router,
    ) as create_router, patch(
        "src.services.inference_orchestration_service.create_orchestrator",
        return_value=orchestrator,
    ) as create_runtime:
        actual = await InferenceOrchestrationService(manager).evaluate_stalled_session(
            session,
            max_iterations=3,
        )

    assert actual is result
    manager.create_snapshot.assert_called_once_with(session.session_id, context)
    create_router.assert_called_once_with(flags)
    create_runtime.assert_called_once_with(
        engine=session.inference_engine,
        session_manager=manager,
        reasoning_router=router,
        feature_flags=flags,
    )
    orchestrator.run_convergence_loop.assert_awaited_once_with(
        session.session_id,
        max_iterations=3,
    )
    assert context.convergence_trace == ["PENDING", "ITERATION_CAP"]


def test_service_builds_context_for_legacy_session_without_one():
    flags = FeatureFlags()
    fact_store = MagicMock()
    assessment_state = MagicMock()
    assessment_state.get_mandatory_list.return_value = ["required"]
    assessment_state.get_fact_store.return_value = fact_store
    engine = MagicMock()
    engine.get_assessment_state.return_value = assessment_state
    session = InferenceSession(
        session_id="legacy-session",
        rule_name="rule",
        target_node_name="goal",
        inference_engine=engine,
        assessment=MagicMock(),
        feature_flags=flags,
        ontology_profile="off",
    )

    context = InferenceOrchestrationService._context_for(session, flags)

    assert session.context is context
    assert context.session_id == session.session_id
    assert context.mandatory == ["required"]
    assert context.fact_store is fact_store
    assert context.ontology_profile == "off"


def test_process_orchestration_service_is_stable():
    assert get_inference_orchestration_service() is get_inference_orchestration_service()
