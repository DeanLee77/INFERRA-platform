"""Application composition for sticky inference orchestration flags."""

from typing import Optional

from src.adapters.outbound.reasoning.factory import create_reasoning_router
from src.domain.inference.session import InferenceSession
from src.domain.session.inference_context import InferenceContext
from src.domain.session.session_manager import ConvergenceResult, SessionManager
from src.domain.state.feature_flags import (
    FeatureFlags,
    get_feature_flags,
    ontology_flags_snapshot,
)
from src.infrastructure.orchestrator_factory import create_orchestrator


class InferenceOrchestrationService:
    """Run the orchestrator/router selected by a session's frozen flags."""

    def __init__(self, session_manager: Optional[SessionManager] = None) -> None:
        self._session_manager = session_manager or SessionManager()

    async def evaluate_stalled_session(
        self,
        session: InferenceSession,
        *,
        max_iterations: int = 10,
    ) -> ConvergenceResult:
        flags = session.feature_flags or get_feature_flags()
        context = self._context_for(session, flags)
        self._session_manager.create_snapshot(session.session_id, context)
        orchestrator = create_orchestrator(
            engine=session.inference_engine,
            session_manager=self._session_manager,
            reasoning_router=create_reasoning_router(flags),
            feature_flags=flags,
        )
        result = await orchestrator.run_convergence_loop(
            session.session_id,
            max_iterations=max_iterations,
        )
        context.convergence_trace = list(result.convergence_trace)
        return result

    @staticmethod
    def _context_for(
        session: InferenceSession,
        flags: FeatureFlags,
    ) -> InferenceContext:
        if isinstance(session.context, InferenceContext):
            return session.context

        assessment_state = session.inference_engine.get_assessment_state()
        context = InferenceContext(
            session_id=session.session_id,
            rule_name=session.rule_name,
            target=session.target_node_name,
            mandatory=list(assessment_state.get_mandatory_list()),
            fact_store=assessment_state.get_fact_store(),
            ontology_profile=session.ontology_profile,
            ontology_profile_source=session.ontology_profile_source,
            ontology_flags=ontology_flags_snapshot(flags),
        )
        session.context = context
        return context


_session_orchestration_service = InferenceOrchestrationService()


def get_inference_orchestration_service() -> InferenceOrchestrationService:
    """Return the process-local orchestration coordinator."""
    return _session_orchestration_service
