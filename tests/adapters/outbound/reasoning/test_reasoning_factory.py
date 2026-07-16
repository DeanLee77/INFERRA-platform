from unittest.mock import MagicMock, patch

from src.adapters.outbound.reasoning.factory import create_reasoning_router
from src.domain.reasoning.null_router import NullReasoningRouter
from src.domain.reasoning.reasoning_router import ReasoningRouter
from src.domain.state.feature_flags import FeatureFlags


def test_reasoning_router_flag_selects_null_router():
    router = create_reasoning_router(FeatureFlags(reasoning_router=False))

    assert isinstance(router, NullReasoningRouter)


def test_reasoning_router_receives_one_frozen_flag_snapshot():
    flags = FeatureFlags(
        reasoning_router=True,
        abduction_enabled=True,
        induction_pipeline=True,
        confidence_thresholds=False,
    )
    flags.freeze()
    abduction = MagicMock()
    induction = MagicMock()

    with patch(
        "src.adapters.outbound.reasoning.factory.create_abduction_adapter",
        return_value=abduction,
    ) as create_abduction, patch(
        "src.adapters.outbound.reasoning.factory.create_induction_adapter",
        return_value=induction,
    ) as create_induction:
        router = create_reasoning_router(flags)

    assert isinstance(router, ReasoningRouter)
    assert router.abduction is abduction
    assert router.induction is induction
    assert router.abduction_enabled is True
    assert router.induction_pipeline is True
    assert router.confidence_thresholds is False
    create_abduction.assert_called_once_with(flags)
    create_induction.assert_called_once_with(flags)
