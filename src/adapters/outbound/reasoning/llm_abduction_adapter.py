import json
import os
from typing import Any, Dict, Iterable, List, Optional, Set

import structlog

from src.adapters.outbound.llm.llm_prompt_sanitizer import LLMPromptSanitizer
from src.domain.reasoning.hypothesis import Hypothesis
from src.ports.abduction_port import AbductionPort

log = structlog.get_logger(__name__)


class LLMAbductionAdapter(AbductionPort):
    """Optional LLM-assisted hypothesis generator behind ABDUCTION_ENABLED."""

    DEFAULT_SYSTEM_PROMPT = (
        "You are an INFERRA rule-based inference diagnostician. "
        "Given an unresolved target fact, propose only plausible missing facts "
        "from the provided dependency graph. Return compact JSON only: a list "
        "of objects with fact_name, suggested_value, confidence, and reasoning."
    )

    def __init__(
        self,
        llm_orchestrator: Any = None,
        *,
        prompt_sanitizer: Optional[type[LLMPromptSanitizer]] = None,
        max_hypotheses: Optional[int] = None,
    ) -> None:
        self._llm = llm_orchestrator
        self._sanitizer = prompt_sanitizer if prompt_sanitizer is not None else LLMPromptSanitizer
        self._max_hypotheses = (
            max_hypotheses
            if max_hypotheses is not None
            else int(os.environ.get("INFERRA_LLM_ABDUCTION_MAX_HYPOTHESES", "5"))
        )

    def propose_hypotheses(
        self,
        target: str,
        working_memory: Dict[str, Any],
        graph_snapshot: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if self._llm is None or not hasattr(self._llm, "chat"):
            log.warning(
                "llm_abduction_unavailable",
                session_id="",
                node_id=target,
                fact_source="HYPOTHETICAL",
                correlation_id="",
            )
            return []

        try:
            prompt = self._sanitizer.sanitize(
                self._build_prompt(target, working_memory, graph_snapshot)
            )
        except ValueError as exc:
            log.warning(
                "llm_abduction_prompt_rejected",
                session_id="",
                node_id=target,
                fact_source="HYPOTHETICAL",
                correlation_id="",
                error=str(exc),
            )
            return []

        try:
            response = self._llm.chat(
                system_prompt=self.DEFAULT_SYSTEM_PROMPT,
                user_prompt=prompt,
                operation="abduction",
                rule_name=target,
            )
        except TypeError:
            response = self._llm.chat(
                system_prompt=self.DEFAULT_SYSTEM_PROMPT,
                user_prompt=prompt,
            )
        except Exception as exc:
            log.warning(
                "llm_abduction_call_failed",
                session_id="",
                node_id=target,
                fact_source="HYPOTHETICAL",
                correlation_id="",
                error=str(exc),
            )
            return []

        allowed_candidates = self._candidate_facts(target, working_memory, graph_snapshot)
        hypotheses = self._parse_response(str(response or ""), target, allowed_candidates)
        hypotheses.sort(key=lambda item: (-item.confidence, item.fact_name))

        log.info(
            "llm_abduction_complete",
            session_id="",
            node_id=target,
            fact_source="HYPOTHETICAL",
            correlation_id="",
            hypothesis_count=len(hypotheses),
            constrained=bool(allowed_candidates),
        )
        return [hypothesis.to_dict() for hypothesis in hypotheses[: self._max_hypotheses]]

    def _build_prompt(
        self,
        target: str,
        working_memory: Dict[str, Any],
        graph_snapshot: Dict[str, Any],
    ) -> str:
        candidates = sorted(self._candidate_facts(target, working_memory, graph_snapshot))
        payload = {
            "target": self._clean_name(target),
            "known_facts": self._compact_mapping(working_memory, limit=30),
            "candidate_missing_facts": candidates[:50],
            "child_groups": self._compact_mapping(
                graph_snapshot.get("child_groups", {}),
                limit=40,
            ),
        }
        return self._truncate(json.dumps(payload, sort_keys=True, default=str), 950)

    def _parse_response(
        self,
        response: str,
        target: str,
        allowed_candidates: Set[str],
    ) -> List[Hypothesis]:
        parsed = self._load_json_payload(response)
        if parsed is None:
            log.warning(
                "llm_abduction_parse_failed",
                session_id="",
                node_id=target,
                fact_source="HYPOTHETICAL",
                correlation_id="",
                response_preview=response[:120],
            )
            return []
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            return []

        hypotheses: List[Hypothesis] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            fact_name = self._clean_name(item.get("fact_name", target))
            if not fact_name:
                continue
            if allowed_candidates and fact_name not in allowed_candidates:
                continue
            hypotheses.append(
                Hypothesis(
                    fact_name=fact_name,
                    suggested_value=self._clean_value(item.get("suggested_value", "true")),
                    confidence=self._confidence(item.get("confidence", 0.5)),
                    dependency_path=[target, fact_name] if target != fact_name else [target],
                    ontology_consistent=bool(item.get("ontology_consistent", True)),
                )
            )
        return hypotheses

    @staticmethod
    def _load_json_payload(response: str) -> Any:
        if not response:
            return None
        try:
            return json.loads(response)
        except (json.JSONDecodeError, TypeError):
            pass

        spans = [
            (response.find("["), response.rfind("]")),
            (response.find("{"), response.rfind("}")),
        ]
        for start, end in spans:
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(response[start : end + 1])
                except (json.JSONDecodeError, TypeError):
                    continue
        return None

    def _candidate_facts(
        self,
        target: str,
        working_memory: Dict[str, Any],
        graph_snapshot: Dict[str, Any],
    ) -> Set[str]:
        child_groups = graph_snapshot.get("child_groups") or {}
        candidates: Set[str] = set()
        seen: Set[str] = set()

        def walk(name: str, depth: int = 0) -> None:
            if depth > 25 or name in seen:
                return
            seen.add(name)
            groups = child_groups.get(name) or ()
            if not groups:
                if name != target and name not in working_memory:
                    candidates.add(name)
                return
            for _, children in self._iter_groups(groups):
                for child in children:
                    walk(str(child), depth + 1)

        walk(target)
        if not candidates:
            nodes = graph_snapshot.get("nodes") or ()
            candidates.update(
                self._clean_name(node)
                for node in nodes
                if self._clean_name(node) and self._clean_name(node) not in working_memory and self._clean_name(node) != target
            )
        return candidates

    @staticmethod
    def _iter_groups(groups: Iterable[Any]) -> Iterable[tuple[Any, Iterable[Any]]]:
        for group in groups:
            if isinstance(group, (list, tuple)) and len(group) >= 2:
                children = group[1] or ()
                yield group[0], children

    @classmethod
    def _compact_mapping(cls, values: Any, *, limit: int) -> Dict[str, str]:
        if not isinstance(values, dict):
            return {}
        compact: Dict[str, str] = {}
        for key in sorted(values, key=str)[:limit]:
            compact[cls._clean_name(key)] = cls._truncate(str(values[key]), 120)
        return compact

    @staticmethod
    def _clean_name(value: Any) -> str:
        return " ".join(str(value or "").replace("\x00", "").split())[:200]

    @staticmethod
    def _clean_value(value: Any) -> str:
        return " ".join(str(value if value is not None else "true").split())[:100]

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        return value if len(value) <= limit else value[: limit - 3] + "..."

