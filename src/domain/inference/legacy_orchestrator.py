from src.domain.inference.inference_engine import InferenceEngine
from src.domain.session.session_manager import ConvergenceResult


class LegacyOrchestrator:
    """Fallback wrapper for sessions not using the Phase 3 orchestrator."""

    def __init__(self, engine: InferenceEngine) -> None:
        self.engine = engine

    async def run_convergence_loop(
        self,
        session_id: str,
        max_iterations: int = 10,
    ) -> ConvergenceResult:
        node_set = self.engine.get_node_set()
        if node_set is None:
            return ConvergenceResult(False, "PENDING", 0, "", 0, session_id=session_id)

        goal = node_set.get_default_goal_node()
        if goal is None:
            return ConvergenceResult(False, "PENDING", 0, "", 0, session_id=session_id)

        state = self.engine.get_assessment_state()
        wm = state.get_working_memory()
        if goal.get_node_name() in wm and state.all_mandatory_node_determined():
            return ConvergenceResult(True, "GOAL_REACHED", 0, "", 0, session_id=session_id)
        return ConvergenceResult(False, "PENDING", 0, "", 0, session_id=session_id)
