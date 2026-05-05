from src.adapters.outbound.reasoning.celery_induction_adapter import CeleryInductionAdapter
from src.adapters.outbound.reasoning.null_abduction_adapter import NullAbductionAdapter
from src.adapters.outbound.reasoning.null_induction_adapter import NullInductionAdapter
from src.adapters.outbound.reasoning.z3_abduction_adapter import Z3AbductionAdapter
from src.domain.state.feature_flags import FeatureFlags
from src.ports.abduction_port import AbductionPort
from src.ports.induction_port import InductionPort


def create_abduction_adapter(flags: FeatureFlags) -> AbductionPort:
    if flags.abduction_enabled:
        return Z3AbductionAdapter()
    return NullAbductionAdapter()


def create_induction_adapter(flags: FeatureFlags) -> InductionPort:
    if flags.induction_pipeline:
        return CeleryInductionAdapter()
    return NullInductionAdapter()
