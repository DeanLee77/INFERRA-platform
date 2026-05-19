from typing import Any, Optional

import structlog

from src.domain.inference.backward_chain_orchestrator import BackwardChainOrchestrator
from src.domain.inference.inference_engine import InferenceEngine
from src.domain.inference.legacy_orchestrator import LegacyOrchestrator
from src.domain.inference.question_strategy import ConservativeQuestionStrategy
from src.domain.state.feature_flags import FeatureFlags
from src.ports.question_strategy_port import QuestionStrategyPort
from src.ports.session_manager_port import SessionManagerPort

log = structlog.get_logger(__name__)


def create_orchestrator(
    engine: InferenceEngine,
    session_manager: SessionManagerPort,
    *,
    strategy: Optional[QuestionStrategyPort] = None,
    reasoning_router: Optional[Any] = None,
    feature_flags: Optional[FeatureFlags] = None,
) -> Any:
    """Create the inference orchestrator selected by sticky feature flags."""
    flags = feature_flags if feature_flags is not None else FeatureFlags()
    if flags.hybrid_orchestrator:
        selected = BackwardChainOrchestrator(
            engine=engine,
            session_manager=session_manager,
            strategy=strategy if strategy is not None else ConservativeQuestionStrategy(),
            reasoning_router=reasoning_router,
        )
        implementation = "BackwardChainOrchestrator"
    else:
        selected = LegacyOrchestrator(engine=engine)
        implementation = "LegacyOrchestrator"

    log.info(
        "orchestrator_created",
        session_id="",
        node_id="",
        fact_source="",
        correlation_id="",
        implementation=implementation,
    )
    return selected

