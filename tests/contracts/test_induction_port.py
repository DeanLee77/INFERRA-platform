from src.adapters.outbound.reasoning.mock_induction_adapter import MockInductionAdapter
from src.adapters.outbound.reasoning.null_induction_adapter import NullInductionAdapter
from src.ports.induction_port import InductionPort


def test_null_induction_adapter_implements_port():
    adapter = NullInductionAdapter()

    assert isinstance(adapter, InductionPort)
    assert adapter.start_batch(["s1"], "rule")["status"] == "disabled"
    assert adapter.get_status("job")["status"] == "disabled"
    assert adapter.promote("job", "rule text")["status"] == "disabled"


def test_mock_induction_adapter_contract_flow():
    adapter = MockInductionAdapter(["INPUT learned_fact AS BOOLEAN"])

    job = adapter.start_batch(["s1", "s2"], "rule")
    status = adapter.get_status(job["job_id"])
    promoted = adapter.promote(job["job_id"], "INPUT learned_fact AS BOOLEAN")

    assert isinstance(adapter, InductionPort)
    assert job["status"] == "completed"
    assert status["candidate_rules"] == ["INPUT learned_fact AS BOOLEAN"]
    assert promoted["status"] == "promoted"
