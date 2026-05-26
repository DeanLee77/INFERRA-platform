from itertools import count
from typing import Iterable

from src.domain.reasoning.induction import InductionJob, InductionResult
from src.services.rule_sandbox import RuleSandbox
from src.ports.induction_port import InductionPort


class MockInductionAdapter(InductionPort):
    """Deterministic induction adapter for tests and demos."""

    def __init__(self, candidate_rules: Iterable[str] | None = None) -> None:
        self._ids = count(1)
        self._candidate_rules = list(candidate_rules or ["INPUT learned_fact AS BOOLEAN"])
        self._jobs: dict[str, dict] = {}

    def start_batch(self, session_ids, rule_name: str) -> dict:
        job_id = f"mock-induction-{next(self._ids)}"
        result = InductionJob(job_id=job_id, status="completed", rule_name=rule_name).to_dict()
        result["session_ids"] = list(session_ids)
        valid_candidates, errors = RuleSandbox().filter_valid_candidates(
            job_id,
            rule_name,
            self._candidate_rules,
        )
        result["candidate_rules"] = valid_candidates
        result["errors"] = errors
        self._jobs[job_id] = result
        return dict(result)

    def get_status(self, job_id: str) -> dict:
        if job_id not in self._jobs:
            return InductionResult(
                job_id=job_id,
                status="not_found",
                errors=["Unknown induction job"],
            ).to_dict()
        result = dict(self._jobs[job_id])
        result.setdefault("errors", [])
        return result

    def promote(self, job_id: str, candidate_rule: str) -> dict:
        if job_id not in self._jobs:
            return InductionResult(
                job_id=job_id,
                status="not_found",
                errors=["Unknown induction job"],
            ).to_dict()
        if candidate_rule not in self._jobs[job_id].get("candidate_rules", []):
            return InductionResult(
                job_id=job_id,
                status="rejected",
                candidate_rules=self._jobs[job_id].get("candidate_rules", []),
                errors=["Candidate rule does not belong to job"],
            ).to_dict()
        return RuleSandbox().promote_candidate(
            job_id,
            candidate_rule,
            self._jobs[job_id].get("candidate_rules", []),
            self._jobs[job_id].get("rule_name", "induced_rule"),
        ).to_dict()
