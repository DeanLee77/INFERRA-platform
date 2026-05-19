from dataclasses import dataclass, field
from typing import Iterable, List

import structlog

from src.services.rule_validation_service import RuleValidationService

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PromotionResult:
    job_id: str
    status: str
    candidate_rules: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    valid: bool = False

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "candidate_rules": list(self.candidate_rules),
            "errors": list(self.errors),
        }


class RuleSandbox:
    """Validation gate for induced candidate rules before human promotion."""

    def __init__(self, validation_service: RuleValidationService | None = None) -> None:
        self._validation = validation_service or RuleValidationService()

    def filter_valid_candidates(
        self,
        job_id: str,
        rule_name: str,
        candidate_rules: Iterable[str],
    ) -> tuple[list[str], list[str]]:
        valid: list[str] = []
        errors: list[str] = []
        for candidate in candidate_rules:
            result = self._validation.validate(candidate, rule_name)
            if result.valid:
                valid.append(candidate)
                continue
            errors.extend(
                f"{candidate}: {error.code} {error.message}"
                for error in result.errors
            )
        log.info(
            "induction_candidates_validated",
            session_id="",
            node_id="",
            fact_source="LEARNED",
            correlation_id=job_id,
            rule_name=rule_name,
            valid_count=len(valid),
            error_count=len(errors),
        )
        return valid, errors

    def promote_candidate(
        self,
        job_id: str,
        candidate_rule: str,
        available_candidates: Iterable[str],
        rule_name: str = "induced_rule",
    ) -> PromotionResult:
        candidates = list(available_candidates)
        if candidate_rule not in candidates:
            return PromotionResult(
                job_id=job_id,
                status="rejected",
                candidate_rules=candidates,
                errors=["Candidate rule does not belong to induction job"],
            )

        result = self._validation.validate(candidate_rule, rule_name)
        if not result.valid:
            return PromotionResult(
                job_id=job_id,
                status="rejected",
                candidate_rules=candidates,
                errors=[f"{error.code}: {error.message}" for error in result.errors],
            )

        return PromotionResult(
            job_id=job_id,
            status="promoted",
            candidate_rules=[candidate_rule],
            valid=True,
        )
