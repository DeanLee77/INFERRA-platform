from src.infrastructure.convergence_metrics import ConvergenceMetrics


def test_convergence_metrics_records_session_summary():
    metrics = ConvergenceMetrics()

    metrics.record_convergence("s1", 3, 12.5, "GOAL_REACHED")
    metrics.record_wm_hash_transition("s1", "old", "new")
    metrics.record_ontology_delta("s1", 2)
    metrics.record_prov_o_triple_count("s1", 42)

    summary = metrics.get_session_metrics("s1")

    assert summary == {
        "iterations": 3,
        "time_to_converge_ms": 12.5,
        "convergence_reason": "GOAL_REACHED",
        "working_memory_hashes": ["new"],
        "ontology_delta_count": 2,
        "prov_o_triple_count": 42,
    }
    assert metrics.get_metrics()["convergence_iterations"] == {"s1": 3}


def test_convergence_metrics_unknown_session_and_clear():
    metrics = ConvergenceMetrics()
    assert metrics.get_session_metrics("missing") is None

    metrics.record_convergence("s1", -1, -5, "PENDING")
    metrics.clear()

    assert metrics.get_session_metrics("s1") is None
    assert metrics.get_metrics()["convergence_iterations"] == {}
