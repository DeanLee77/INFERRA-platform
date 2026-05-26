from src.domain.reasoning.induction import InductionJob, InductionResult
from src.ports.induction_port import InductionPort


class NullInductionAdapter(InductionPort):
    """No-op induction adapter for INDUCTION_PIPELINE=false."""

    def start_batch(self, session_ids, rule_name: str) -> dict:
        return InductionJob(job_id="", status="disabled", rule_name=rule_name).to_dict()

    def get_status(self, job_id: str) -> dict:
        return InductionResult(job_id=job_id, status="disabled").to_dict()

    def promote(self, job_id: str, candidate_rule: str) -> dict:
        return InductionResult(job_id=job_id, status="disabled").to_dict()
