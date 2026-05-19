import re
from typing import Iterable, List

import structlog

from src.domain.reasoning.pattern_miner import MinedRuleCandidate
from src.domain.state.fact_source import FactSource

log = structlog.get_logger(__name__)


class InferraCompiler:
    """Compile mined candidates into conservative INFERRA rule text."""

    def compile(self, candidate: MinedRuleCandidate) -> str:
        antecedents = self._unique_safe_names(candidate.antecedents)
        consequent_name = self._safe_name(candidate.consequent)
        antecedents = tuple(name for name in antecedents if name != consequent_name)
        if not antecedents:
            log.warning(
                "compiler_no_antecedents",
                session_id="",
                node_id=candidate.consequent,
                fact_source=FactSource.LEARNED.value,
                correlation_id=candidate.candidate_id,
                rule_name=candidate.consequent,
            )
            return ""

        lines: List[str] = [f"INPUT {name} AS BOOLEAN" for name in antecedents]
        lines.append(f"{consequent_name} IS true")
        lines.extend(f"    {name} IS true" for name in antecedents)
        compiled = "\n".join(lines)

        log.info(
            "compilation_complete",
            session_id="",
            node_id=consequent_name,
            fact_source=FactSource.LEARNED.value,
            correlation_id=candidate.candidate_id,
            rule_name=consequent_name,
            support=candidate.support,
            confidence=candidate.confidence,
        )
        return compiled

    def compile_batch(self, candidates: Iterable[MinedRuleCandidate]) -> List[str]:
        compiled: List[str] = []
        for candidate in candidates:
            rule_text = self.compile(candidate)
            if rule_text:
                compiled.append(rule_text)
        return compiled

    @classmethod
    def _safe_name(cls, name: str) -> str:
        sanitized = re.sub(r"[^0-9A-Za-z_]+", "_", str(name).strip())
        sanitized = re.sub(r"_+", "_", sanitized).strip("_")
        if sanitized and sanitized[0].isdigit():
            sanitized = "_" + sanitized
        return sanitized or "unnamed"

    @classmethod
    def _unique_safe_names(cls, names: Iterable[str]) -> tuple[str, ...]:
        result: List[str] = []
        seen = set()
        for name in names:
            safe = cls._safe_name(name)
            if safe in seen:
                continue
            seen.add(safe)
            result.append(safe)
        return tuple(result)
