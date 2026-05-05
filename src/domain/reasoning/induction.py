from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class InductionJob:
    job_id: str
    status: str
    rule_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "rule_name": self.rule_name,
        }


@dataclass(frozen=True)
class InductionResult:
    job_id: str
    status: str
    candidate_rules: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "candidate_rules": list(self.candidate_rules),
            "errors": list(self.errors),
        }
