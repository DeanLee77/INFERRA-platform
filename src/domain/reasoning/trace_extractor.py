import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

import structlog

from src.domain.state.fact_source import FactSource

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class TracePattern:
    """A compact, mineable summary of facts observed in one or more sessions."""

    pattern_id: str
    fact_names: Tuple[str, ...]
    decision_path: Tuple[str, ...]
    frequency: int
    rule_name: str = ""


class TraceExtractor:
    """Extract recurring fact patterns from PROV-O traces or session snapshots."""

    INFERRA_NS = "https://inferra.local/ns#"
    PROV_NS = "http://www.w3.org/ns/prov#"

    def extract(self, prov_o_trace: str, session_id: str = "", rule_name: str = "") -> List[TracePattern]:
        if not prov_o_trace or not prov_o_trace.strip():
            return []

        try:
            from rdflib import Graph, Namespace, RDF
        except ImportError:
            log.warning(
                "trace_extractor_rdflib_missing",
                session_id=session_id,
                node_id="",
                fact_source=FactSource.LEARNED.value,
                correlation_id=session_id,
                rule_name=rule_name,
            )
            return []

        graph = Graph()
        parsed = False
        for fmt in ("turtle", "json-ld"):
            try:
                graph.parse(data=prov_o_trace, format=fmt)
                parsed = True
                break
            except Exception:
                graph = Graph()
        if not parsed:
            log.warning(
                "trace_extractor_parse_failed",
                session_id=session_id,
                node_id="",
                fact_source=FactSource.LEARNED.value,
                correlation_id=session_id,
                rule_name=rule_name,
            )
            return []

        inf = Namespace(self.INFERRA_NS)
        prov = Namespace(self.PROV_NS)
        facts_by_session: Dict[str, List[Tuple[str, Any]]] = {}

        for subject, _, _ in graph.triples((None, RDF.type, inf.Conclusion)):
            fact_name = graph.value(subject, inf.name)
            if fact_name is None:
                continue
            session_uri = graph.value(subject, prov.wasGeneratedBy)
            bucket = str(session_uri or session_id or "unknown")
            facts_by_session.setdefault(bucket, []).append(
                (str(fact_name), graph.value(subject, inf.value))
            )

        patterns = [
            self._pattern_from_items(items, session_id=bucket, rule_name=rule_name)
            for bucket, items in facts_by_session.items()
            if items
        ]
        merged = self._merge_patterns([pattern for pattern in patterns if pattern is not None])
        log.info(
            "trace_extraction_complete",
            session_id=session_id,
            node_id="",
            fact_source=FactSource.LEARNED.value,
            correlation_id=session_id,
            rule_name=rule_name,
            pattern_count=len(merged),
        )
        return merged

    def extract_from_dict(
        self,
        session_data: Dict[str, Any],
        session_id: str = "",
        rule_name: str = "",
    ) -> List[TracePattern]:
        working_memory = session_data.get("working_memory", {}) if isinstance(session_data, dict) else {}
        if not isinstance(working_memory, dict) or not working_memory:
            return []

        effective_rule = rule_name or str(session_data.get("metadata", {}).get("rule_name", ""))
        pattern = self._pattern_from_items(
            sorted(working_memory.items()),
            session_id=session_id,
            rule_name=effective_rule,
        )
        return [] if pattern is None else [pattern]

    def _pattern_from_items(
        self,
        items: Iterable[Tuple[str, Any]],
        *,
        session_id: str,
        rule_name: str,
    ) -> TracePattern | None:
        facts: List[str] = []
        decisions: List[str] = []
        for raw_name, raw_value in items:
            name = str(raw_name).strip()
            if not name:
                continue
            value = self._unwrap_value(raw_value)
            facts.append(name)
            if isinstance(value, bool):
                decisions.append(name)
            elif isinstance(value, str) and value.lower() in {"true", "false"}:
                decisions.append(name)

        if not facts:
            return None

        fact_tuple = tuple(sorted(set(facts)))
        decision_tuple = tuple(name for name in fact_tuple if name in set(decisions))
        return TracePattern(
            pattern_id=self._pattern_id(fact_tuple, decision_tuple, rule_name),
            fact_names=fact_tuple,
            decision_path=decision_tuple,
            frequency=1,
            rule_name=rule_name,
        )

    def _merge_patterns(self, patterns: List[TracePattern]) -> List[TracePattern]:
        buckets: Dict[Tuple[Tuple[str, ...], Tuple[str, ...], str], List[TracePattern]] = {}
        for pattern in patterns:
            key = (pattern.fact_names, pattern.decision_path, pattern.rule_name)
            buckets.setdefault(key, []).append(pattern)

        merged: List[TracePattern] = []
        for (fact_names, decision_path, rule_name), group in buckets.items():
            merged.append(
                TracePattern(
                    pattern_id=self._pattern_id(fact_names, decision_path, rule_name),
                    fact_names=fact_names,
                    decision_path=decision_path,
                    frequency=sum(pattern.frequency for pattern in group),
                    rule_name=rule_name,
                )
            )
        merged.sort(key=lambda pattern: (-pattern.frequency, pattern.pattern_id))
        return merged

    @staticmethod
    def _unwrap_value(value: Any) -> Any:
        if hasattr(value, "get_value"):
            return value.get_value()
        if isinstance(value, dict) and "value" in value:
            return value["value"]
        return value

    @staticmethod
    def _pattern_id(
        fact_names: Tuple[str, ...],
        decision_path: Tuple[str, ...],
        rule_name: str,
    ) -> str:
        payload = {
            "facts": fact_names,
            "decision_path": decision_path,
            "rule_name": rule_name,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        return f"tp_{digest[:12]}"
