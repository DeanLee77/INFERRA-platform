from datetime import datetime

from src.domain.fact_values import FactValue
from src.domain.session import InferenceContext, SessionManager
from src.domain.state import FactSource, LayeredFactStore


def _ctx(session_id="s1", target="goal", mandatory=None):
    store = LayeredFactStore()
    return InferenceContext(
        session_id=session_id,
        rule_name="rule",
        target=target,
        mandatory=mandatory or [],
        fact_store=store,
        started_at=datetime.utcnow(),
    )


def test_convergence_goal_reached_when_goal_and_mandatory_known():
    mgr = SessionManager()
    ctx = _ctx(mandatory=["m1"])
    ctx.fact_store.set_fact("goal", FactValue(True), FactSource.INFERRED)
    ctx.fact_store.set_fact("m1", FactValue(True), FactSource.ASSERTED)
    mgr.create_snapshot("s1", ctx)

    result = mgr.check_convergence("s1")

    assert result.converged is True
    assert result.reason == "GOAL_REACHED"


def test_convergence_fixed_point_after_stable_hash():
    mgr = SessionManager()
    ctx = _ctx()
    ctx.fact_store.set_fact("goal", FactValue(True), FactSource.INFERRED)
    mgr.create_snapshot("s1", ctx)

    first = mgr.check_convergence("s1")
    second = mgr.check_convergence("s1")

    assert first.reason == "GOAL_REACHED"
    assert second.reason == "FIXED_POINT"
    assert first.working_memory_hash == second.working_memory_hash


def test_hash_is_independent_of_insert_order():
    mgr = SessionManager()
    store_a = LayeredFactStore()
    store_b = LayeredFactStore()
    store_a.set_fact("a", FactValue(1), FactSource.ASSERTED)
    store_a.set_fact("b", FactValue(2), FactSource.INFERRED)
    store_b.set_fact("b", FactValue(2), FactSource.INFERRED)
    store_b.set_fact("a", FactValue(1), FactSource.ASSERTED)

    assert mgr._compute_wm_hash(store_a.get_unified_view()) == mgr._compute_wm_hash(store_b.get_unified_view())


def test_lru_eviction_removes_oldest_snapshot():
    mgr = SessionManager(max_snapshots=1)
    mgr.create_snapshot("s1", _ctx("s1"))
    mgr.create_snapshot("s2", _ctx("s2"))

    assert mgr.get_snapshot("s1") is None
    assert mgr.get_snapshot("s2") is not None


def test_snapshot_expires_after_ttl():
    now = [100.0]
    mgr = SessionManager(ttl_seconds=10, clock=lambda: now[0])
    mgr.create_snapshot("s1", _ctx("s1"))

    now[0] = 111.0

    assert mgr.get_snapshot("s1") is None
    assert mgr.snapshot_count == 0


def test_check_convergence_returns_pending_for_missing_snapshot():
    result = SessionManager().check_convergence("missing")

    assert result.converged is False
    assert result.reason == "PENDING"
    assert result.session_id == "missing"


def test_goal_reached_stable_allows_pending_ontology_delta():
    mgr = SessionManager()
    ctx = _ctx()
    ctx.fact_store.set_fact("goal", FactValue(True), FactSource.INFERRED)
    ctx.set_ontology_delta(1)
    mgr.create_snapshot("s1", ctx)

    first = mgr.check_convergence("s1")
    second = mgr.check_convergence("s1")

    assert first.reason == "GOAL_REACHED"
    assert second.reason == "GOAL_REACHED_STABLE"


def test_canonical_hash_handles_plain_nested_values():
    mgr = SessionManager()
    first = {
        "plain": {
            "b": [FactValue(2), 3],
            "a": "x",
        }
    }
    second = {
        "plain": {
            "a": "x",
            "b": [FactValue(2), 3],
        }
    }

    assert mgr._compute_wm_hash(first) == mgr._compute_wm_hash(second)


def test_inference_context_records_phase5_abduction_state():
    ctx = _ctx()

    ctx.record_abduction_attempt(
        [
            {
                "fact_name": "missing",
                "suggested_value": "true",
                "confidence": 0.82,
            }
        ]
    )

    assert ctx.reasoning_mode == "ABDUCTION"
    assert ctx.abduction_attempted is True
    assert ctx.abduction_count == 1
    assert ctx.confidence == 0.82
    assert ctx.hypothesis_trace[0]["fact_name"] == "missing"


def test_inference_context_records_phase5_induction_state():
    ctx = _ctx()

    ctx.set_induction_job("job-1")

    assert ctx.reasoning_mode == "INDUCTION"
    assert ctx.induction_job_id == "job-1"
    assert ctx.confidence == 0.5
