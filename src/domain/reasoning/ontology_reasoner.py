"""Materialized ontology reasoning for session-frozen RDF snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.domain.fact_values import FactValue, FactValueType
from src.domain.reasoning.semantic_fact_enricher import (
    OWL_EQUIVALENT_CLASS,
    RDF_TYPE,
    RDFS_SUBCLASS_OF,
    OntologyIndex,
)
from src.domain.state.fact_source import FactSource
from src.ports.fact_store_port import FactStorePort


@dataclass(frozen=True)
class OntologyDerivedFact:
    """A fact approved for materialization into the INFERRED layer."""

    fact_name: str
    fact_value: FactValue
    source_fact_name: str
    source_value: Any
    source_iri: str
    ontology_iri: str
    confidence: float
    source_graph_uri: str
    ontology_snapshot_ref: str
    ontology_snapshot_hash: Optional[str]
    derivation_rule: str
    derivation_path: Tuple[str, ...]
    hierarchy_depth: int
    missing_prerequisites: Tuple[str, ...] = ()
    expected_information_gain: int = 0

    def to_trace(self) -> Dict[str, Any]:
        return {
            "status": "materialized",
            "factName": self.fact_name,
            "value": self.fact_value.get_value(),
            "valueType": self.fact_value.get_value_type().value,
            "factSource": FactSource.INFERRED.value,
            "sourceFactName": self.source_fact_name,
            "sourceValue": self.source_value,
            "sourceIri": self.source_iri,
            "ontologyIri": self.ontology_iri,
            "sourceGraphUri": self.source_graph_uri,
            "ontologySnapshotRef": self.ontology_snapshot_ref,
            "ontologySnapshotHash": self.ontology_snapshot_hash,
            "confidence": self.confidence,
            "derivationRule": self.derivation_rule,
            "derivationPath": list(self.derivation_path),
            "hierarchyDepth": self.hierarchy_depth,
            "missingPrerequisites": list(self.missing_prerequisites),
            "expectedInformationGain": self.expected_information_gain,
            "materializedInference": True,
            "abstentionCause": None,
            "contradictionCause": None,
        }


@dataclass(frozen=True)
class OntologyMaterializationResult:
    """Materialization output plus audit events for accepted and abstained paths."""

    derived_facts: Tuple[OntologyDerivedFact, ...]
    trace: Tuple[Dict[str, Any], ...]


@dataclass(frozen=True)
class _ClassPath:
    iri: str
    path: Tuple[str, ...]
    depth: int
    derivation_rule: str


class OntologyReasoner:
    """Derive grounded boolean facts from RDF type and class hierarchy closure."""

    def __init__(
        self,
        *,
        source_graph_uri: str,
        ontology_snapshot_ref: str,
        ontology_snapshot_hash: Optional[str],
        confidence_threshold: float = 0.85,
        min_hierarchy_depth: int = 1,
        max_closure_depth: int = 10,
    ) -> None:
        self.source_graph_uri = source_graph_uri
        self.ontology_snapshot_ref = ontology_snapshot_ref
        self.ontology_snapshot_hash = ontology_snapshot_hash
        self.confidence_threshold = confidence_threshold
        self.min_hierarchy_depth = max(0, min_hierarchy_depth)
        self.max_closure_depth = max(1, max_closure_depth)

    def materialize(
        self,
        fact_name: str,
        fact_value: FactValue,
        ontology_index: OntologyIndex,
        *,
        fact_store: Optional[FactStorePort] = None,
    ) -> OntologyMaterializationResult:
        """Return ontology-derived facts approved for INFERRED materialization."""
        trace: List[Dict[str, Any]] = []
        derived: List[OntologyDerivedFact] = []
        seen_facts: set[str] = set()

        if not self.ontology_snapshot_hash:
            trace.append(
                self._abstain_event(
                    fact_name=fact_name,
                    source_value=fact_value.get_value(),
                    cause="stale_or_unversioned_ontology_snapshot",
                )
            )
            return OntologyMaterializationResult((), tuple(trace))

        for value in self._iter_fact_values(fact_value):
            value_subjects = ontology_index.subjects_for_label(value)
            if len(value_subjects) != 1:
                trace.append(
                    self._abstain_event(
                        fact_name=fact_name,
                        source_value=value,
                        cause=(
                            "ungrounded_value_binding"
                            if not value_subjects
                            else "ambiguous_value_binding"
                        ),
                        candidates=value_subjects,
                    )
                )
                continue

            source_iri = value_subjects[0]
            for class_path in self._class_paths(source_iri, ontology_index):
                if class_path.depth < self.min_hierarchy_depth:
                    continue
                confidence = self._path_confidence(
                    class_path.path,
                    ontology_index,
                )
                if confidence < self.confidence_threshold:
                    trace.append(
                        self._abstain_event(
                            fact_name=fact_name,
                            source_value=value,
                            source_iri=source_iri,
                            ontology_iri=class_path.iri,
                            cause="below_confidence_threshold",
                            confidence=confidence,
                            derivation_rule=class_path.derivation_rule,
                            derivation_path=class_path.path,
                            hierarchy_depth=class_path.depth,
                        )
                    )
                    continue

                target_names = ontology_index.labels_for_subject(class_path.iri)
                if not target_names:
                    trace.append(
                        self._abstain_event(
                            fact_name=fact_name,
                            source_value=value,
                            source_iri=source_iri,
                            ontology_iri=class_path.iri,
                            cause="unsupported_unlabeled_target",
                            confidence=confidence,
                            derivation_rule=class_path.derivation_rule,
                            derivation_path=class_path.path,
                            hierarchy_depth=class_path.depth,
                        )
                    )
                    continue

                for target_name in target_names:
                    if target_name == fact_name or str(target_name) == str(value):
                        continue
                    target_subjects = ontology_index.subjects_for_label(target_name)
                    if len(target_subjects) != 1:
                        trace.append(
                            self._abstain_event(
                                fact_name=str(target_name),
                                source_value=value,
                                source_iri=source_iri,
                                ontology_iri=class_path.iri,
                                cause="ambiguous_target_binding",
                                candidates=target_subjects,
                                confidence=confidence,
                                derivation_rule=class_path.derivation_rule,
                                derivation_path=class_path.path,
                                hierarchy_depth=class_path.depth,
                            )
                        )
                        continue

                    if target_name in seen_facts:
                        continue
                    overwrite_event = self._overwrite_guard_event(
                        target_name,
                        fact_store,
                        source_value=value,
                        source_iri=source_iri,
                        ontology_iri=class_path.iri,
                        confidence=confidence,
                        derivation_rule=class_path.derivation_rule,
                        derivation_path=class_path.path,
                        hierarchy_depth=class_path.depth,
                    )
                    if overwrite_event is not None:
                        trace.append(overwrite_event)
                        continue

                    derived_fact = OntologyDerivedFact(
                        fact_name=str(target_name),
                        fact_value=FactValue(True, FactValueType.BOOLEAN),
                        source_fact_name=fact_name,
                        source_value=value,
                        source_iri=source_iri,
                        ontology_iri=class_path.iri,
                        confidence=confidence,
                        source_graph_uri=self.source_graph_uri,
                        ontology_snapshot_ref=self.ontology_snapshot_ref,
                        ontology_snapshot_hash=self.ontology_snapshot_hash,
                        derivation_rule=class_path.derivation_rule,
                        derivation_path=class_path.path,
                        hierarchy_depth=class_path.depth,
                        missing_prerequisites=tuple(
                            self.missing_prerequisites(
                                str(target_name),
                                ontology_index,
                            )
                        ),
                        expected_information_gain=self.estimate_information_gain(
                            str(target_name),
                            ontology_index,
                        ),
                    )
                    derived.append(derived_fact)
                    trace.append(derived_fact.to_trace())
                    seen_facts.add(str(target_name))

        return OntologyMaterializationResult(
            tuple(derived),
            tuple(trace),
        )

    def can_derive(
        self,
        fact_name: str,
        fact_store: FactStorePort,
        ontology_index: OntologyIndex,
    ) -> Tuple[bool, Optional[FactValue], float]:
        """Check whether current facts can derive the requested fact."""
        best_confidence = 0.0
        for source_name, source_value in sorted(fact_store.get_unified_view().items()):
            result = self.materialize(
                source_name,
                source_value,
                ontology_index,
                fact_store=fact_store,
            )
            for derived in result.derived_facts:
                if derived.fact_name == fact_name:
                    return True, derived.fact_value, derived.confidence
                best_confidence = max(best_confidence, derived.confidence)
        return False, None, best_confidence

    def missing_prerequisites(
        self,
        fact_name: str,
        ontology_index: OntologyIndex,
    ) -> List[str]:
        """Return source labels whose known values could derive the target fact."""
        target_subjects = ontology_index.subjects_for_label(fact_name)
        if len(target_subjects) != 1:
            return []
        target_iri = target_subjects[0]
        prerequisites: set[str] = set()
        for instance in ontology_index.get_instances(target_iri):
            prerequisites.update(ontology_index.labels_for_subject(instance))
        for subclass in ontology_index.get_subclasses(target_iri):
            prerequisites.update(ontology_index.labels_for_subject(subclass))
            for instance in ontology_index.get_instances(subclass):
                prerequisites.update(ontology_index.labels_for_subject(instance))
        return sorted(item for item in prerequisites if item != fact_name)

    def estimate_information_gain(
        self,
        fact_name: str,
        ontology_index: OntologyIndex,
    ) -> int:
        """Estimate how many labeled facts could be unlocked by a source fact."""
        subjects = ontology_index.subjects_for_label(fact_name)
        if len(subjects) != 1:
            return 0
        labels: set[str] = set()
        for class_path in self._class_paths(subjects[0], ontology_index):
            labels.update(ontology_index.labels_for_subject(class_path.iri))
        labels.discard(fact_name)
        return len(labels)

    def _class_paths(
        self,
        source_iri: str,
        ontology_index: OntologyIndex,
    ) -> Tuple[_ClassPath, ...]:
        queue: List[_ClassPath] = []
        for class_iri in ontology_index.objects(source_iri, RDF_TYPE):
            queue.append(
                _ClassPath(
                    iri=class_iri,
                    path=(source_iri, RDF_TYPE, class_iri),
                    depth=1,
                    derivation_rule="rdf_type_subclass_closure",
                )
            )
        if ontology_index.objects(source_iri, RDFS_SUBCLASS_OF) or ontology_index.get_equivalent_classes(source_iri):
            queue.append(
                _ClassPath(
                    iri=source_iri,
                    path=(source_iri,),
                    depth=0,
                    derivation_rule="rdfs_subclass_closure",
                )
            )

        visited = {(item.iri, item.depth) for item in queue}
        results: List[_ClassPath] = []
        while queue:
            current = queue.pop(0)
            if current.depth > self.max_closure_depth:
                continue
            results.append(current)
            if current.depth >= self.max_closure_depth:
                continue

            for target in ontology_index.objects(current.iri, RDFS_SUBCLASS_OF):
                key = (target, current.depth + 1)
                if key in visited:
                    continue
                visited.add(key)
                queue.append(
                    _ClassPath(
                        iri=target,
                        path=(*current.path, RDFS_SUBCLASS_OF, target),
                        depth=current.depth + 1,
                        derivation_rule="rdfs_subclass_closure",
                    )
                )

            for target in ontology_index.get_equivalent_classes(current.iri):
                key = (target, current.depth + 1)
                if key in visited:
                    continue
                visited.add(key)
                queue.append(
                    _ClassPath(
                        iri=target,
                        path=(*current.path, OWL_EQUIVALENT_CLASS, target),
                        depth=current.depth + 1,
                        derivation_rule="owl_equivalent_class_closure",
                    )
                )

        return tuple(results)

    def _path_confidence(
        self,
        path: Sequence[str],
        ontology_index: OntologyIndex,
    ) -> float:
        confidences = [
            ontology_index.confidence_for(iri, 1.0)
            for iri in path
            if _looks_like_iri(iri)
        ]
        return min(confidences) if confidences else 1.0

    def _iter_fact_values(self, fact_value: FactValue) -> Tuple[Any, ...]:
        value = fact_value.get_value()
        if fact_value.get_value_type() == FactValueType.LIST and isinstance(value, list):
            return tuple(_unwrap_fact_value(item) for item in value)
        return (_unwrap_fact_value(value),)

    def _overwrite_guard_event(
        self,
        fact_name: str,
        fact_store: Optional[FactStorePort],
        *,
        source_value: Any,
        source_iri: str,
        ontology_iri: str,
        confidence: float,
        derivation_rule: str,
        derivation_path: Sequence[str],
        hierarchy_depth: int,
    ) -> Optional[Dict[str, Any]]:
        if fact_store is None:
            return None

        sources = fact_store.get_fact_sources(fact_name)
        if not sources:
            return None
        if sources == {FactSource.SEMANTIC}:
            return None

        existing = fact_store.peek_in_layer(fact_name, FactSource.ASSERTED)
        if existing is not None:
            cause = (
                "asserted_fact_conflict"
                if existing.get_value() is not True
                else "asserted_fact_exists"
            )
            return self._abstain_event(
                fact_name=fact_name,
                source_value=source_value,
                source_iri=source_iri,
                ontology_iri=ontology_iri,
                cause=cause,
                contradiction_cause=(
                    cause if cause == "asserted_fact_conflict" else None
                ),
                confidence=confidence,
                derivation_rule=derivation_rule,
                derivation_path=derivation_path,
                hierarchy_depth=hierarchy_depth,
            )

        existing = fact_store.get_unified_view().get(fact_name)
        if existing is not None:
            cause = (
                "existing_deterministic_fact_conflict"
                if existing.get_value() is not True
                else "deterministic_fact_exists"
            )
            return self._abstain_event(
                fact_name=fact_name,
                source_value=source_value,
                source_iri=source_iri,
                ontology_iri=ontology_iri,
                cause=cause,
                contradiction_cause=(
                    cause if cause == "existing_deterministic_fact_conflict" else None
                ),
                confidence=confidence,
                derivation_rule=derivation_rule,
                derivation_path=derivation_path,
                hierarchy_depth=hierarchy_depth,
            )
        return None

    def _abstain_event(
        self,
        *,
        fact_name: str,
        source_value: Any,
        cause: str,
        source_iri: Optional[str] = None,
        ontology_iri: Optional[str] = None,
        candidates: Iterable[str] = (),
        confidence: float = 0.0,
        derivation_rule: Optional[str] = None,
        derivation_path: Sequence[str] = (),
        hierarchy_depth: Optional[int] = None,
        contradiction_cause: Optional[str] = None,
        missing_prerequisites: Sequence[str] = (),
        expected_information_gain: int = 0,
    ) -> Dict[str, Any]:
        return {
            "status": "abstained",
            "factName": fact_name,
            "sourceValue": source_value,
            "sourceIri": source_iri,
            "ontologyIri": ontology_iri,
            "sourceGraphUri": self.source_graph_uri,
            "ontologySnapshotRef": self.ontology_snapshot_ref,
            "ontologySnapshotHash": self.ontology_snapshot_hash,
            "confidence": confidence,
            "derivationRule": derivation_rule,
            "derivationPath": list(derivation_path),
            "hierarchyDepth": hierarchy_depth,
            "missingPrerequisites": list(missing_prerequisites),
            "expectedInformationGain": expected_information_gain,
            "materializedInference": False,
            "abstentionCause": cause,
            "contradictionCause": contradiction_cause,
            "candidateIris": list(candidates),
        }


def _unwrap_fact_value(value: Any) -> Any:
    if hasattr(value, "get_value"):
        return value.get_value()
    return value


def _looks_like_iri(value: str) -> bool:
    return "://" in value or value.startswith("urn:")
