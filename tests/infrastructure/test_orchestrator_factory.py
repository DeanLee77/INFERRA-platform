from unittest.mock import MagicMock

from src.domain.inference.backward_chain_orchestrator import BackwardChainOrchestrator
from src.domain.inference.legacy_orchestrator import LegacyOrchestrator
from src.domain.state.feature_flags import FeatureFlags
from src.infrastructure.orchestrator_factory import create_orchestrator


def test_create_orchestrator_selects_backward_chain_when_hybrid_enabled():
    strategy = MagicMock()
    router = MagicMock()

    orchestrator = create_orchestrator(
        engine=MagicMock(),
        session_manager=MagicMock(),
        strategy=strategy,
        reasoning_router=router,
        feature_flags=FeatureFlags(hybrid_orchestrator=True),
    )

    assert isinstance(orchestrator, BackwardChainOrchestrator)
    assert orchestrator.strategy is strategy
    assert orchestrator.reasoning_router is router


def test_create_orchestrator_selects_legacy_when_hybrid_disabled():
    engine = MagicMock()

    orchestrator = create_orchestrator(
        engine=engine,
        session_manager=MagicMock(),
        feature_flags=FeatureFlags(hybrid_orchestrator=False),
    )

    assert isinstance(orchestrator, LegacyOrchestrator)
    assert orchestrator.engine is engine

