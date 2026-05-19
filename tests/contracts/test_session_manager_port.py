from src.domain.fact_values import FactValue
from src.domain.session import InferenceContext, SessionManager
from src.domain.state import FactSource, LayeredFactStore
from src.ports.session_manager_port import SessionManagerPort


def _ctx():
    store = LayeredFactStore()
    store.set_fact("goal", FactValue(True), FactSource.INFERRED)
    return InferenceContext(
        session_id="contract",
        rule_name="rule",
        target="goal",
        mandatory=[],
        fact_store=store,
    )


def test_session_manager_implements_port():
    assert isinstance(SessionManager(), SessionManagerPort)


def test_create_snapshot_then_check_convergence_contract():
    manager = SessionManager()
    manager.create_snapshot("contract", _ctx())

    result = manager.check_convergence("contract")

    assert result.converged is True
    assert manager.get_wm_hash("contract") == result.working_memory_hash


def test_remove_snapshot_cleans_up_contract():
    manager = SessionManager()
    manager.create_snapshot("contract", _ctx())
    manager.check_convergence("contract")

    manager.remove_snapshot("contract")

    assert manager.get_snapshot("contract") is None
    assert manager.get_wm_hash("contract") == ""
