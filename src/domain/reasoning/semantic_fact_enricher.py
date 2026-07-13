"""Semantic fact enrichment over an in-memory OWL/RDFS-aligned subset."""

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.domain.fact_values import FactValue
from src.domain.state.fact_source import FactSource
from src.ports.fact_store_port import FactStorePort

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_SUBCLASS_OF = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
RDFS_SUBPROPERTY_OF = "http://www.w3.org/2000/01/rdf-schema#subPropertyOf"
RDFS_DOMAIN = "http://www.w3.org/2000/01/rdf-schema#domain"
RDFS_RANGE = "http://www.w3.org/2000/01/rdf-schema#range"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
OWL_EQUIVALENT_CLASS = "http://www.w3.org/2002/07/owl#equivalentClass"
INF_NS = "http://inferra.ai/schema#"
INF_NAME = f"{INF_NS}name"
INF_HAS_ITEM = f"{INF_NS}hasItem"
INF_VALUE_TYPE = f"{INF_NS}valueType"
INF_DEFAULT_VALUE = f"{INF_NS}defaultValue"
INF_CONFIDENCE = f"{INF_NS}confidence"
INF_MINIMUM = f"{INF_NS}minimum"
INF_MAXIMUM = f"{INF_NS}maximum"

OntologyTriple = Tuple[str, str, str]


@dataclass(frozen=True)
class BoundFact:
    """Binds an asserted fact to the RDF statement that describes it."""

    fact_name: str
    subject_iri: str
    predicate_iri: str
    object_iri: str
    confidence: float = 1.0
    source_graph_uri: str = "in_memory_triples"


@dataclass(frozen=True)
class OntologyBindingEvidence:
    """Deterministic fact-to-ontology binding evidence."""

    fact_name: str
    ontology_iri: str
    matched_label: str
    matched_predicate: str
    source_graph_uri: str
    confidence: float = 1.0
    status: str = "bound"
    source_label: str = FactSource.SEMANTIC.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "factName": self.fact_name,
            "ontologyIri": self.ontology_iri,
            "matchedLabel": self.matched_label,
            "matchedPredicate": _compact_relationship(self.matched_predicate),
            "sourceGraphUri": self.source_graph_uri,
            "confidence": self.confidence,
            "status": self.status,
            "sourceLabel": self.source_label,
        }


@dataclass(frozen=True)
class OntologyBindingIssue:
    """Missing or ambiguous binding evidence for a rule fact."""

    fact_name: str
    status: str
    candidates: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "factName": self.fact_name,
            "status": self.status,
            "candidates": list(self.candidates),
            "sourceLabel": FactSource.SEMANTIC.value,
        }


@dataclass(frozen=True)
class OntologyBindingReport:
    """Result of deterministic ontology binding resolution."""

    bindings: Tuple[OntologyBindingEvidence, ...]
    ambiguous: Tuple[OntologyBindingIssue, ...]
    missing: Tuple[OntologyBindingIssue, ...]

    def binding_by_fact(self) -> Dict[str, OntologyBindingEvidence]:
        return {item.fact_name: item for item in self.bindings}

    def to_trace(self) -> Dict[str, Any]:
        return {
            "bindings": [item.to_dict() for item in self.bindings],
            "ambiguous": [item.to_dict() for item in self.ambiguous],
            "missing": [item.to_dict() for item in self.missing],
            "bindingCount": len(self.bindings),
            "ambiguityCount": len(self.ambiguous),
            "missingCount": len(self.missing),
        }


@dataclass(frozen=True)
class SemanticSuggestion:
    """Response-only ontology advisory evidence for a user question."""

    fact_name: str
    ontology_iri: str
    relationship: str
    suggested_value: Optional[Any]
    confidence: float
    source_graph_uri: str
    ontology_snapshot_ref: str
    ontology_snapshot_hash: Optional[str] = None
    source_label: str = FactSource.SEMANTIC.value
    advisory_only: bool = True
    alters_deterministic_outcome: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "factName": self.fact_name,
            "ontologyIri": self.ontology_iri,
            "relationship": self.relationship,
            "suggestedValue": self.suggested_value,
            "confidence": self.confidence,
            "sourceGraphUri": self.source_graph_uri,
            "ontologySnapshotRef": self.ontology_snapshot_ref,
            "ontologySnapshotHash": self.ontology_snapshot_hash,
            "sourceLabel": self.source_label,
            "advisoryOnly": self.advisory_only,
            "altersDeterministicOutcome": self.alters_deterministic_outcome,
        }


@dataclass(frozen=True)
class OntologyValueSuggestion:
    """Candidate ontology default that may pre-fill or auto-answer a question."""

    fact_name: str
    ontology_iri: str
    relationship: str
    suggested_value: Any
    confidence: float
    basis: str
    source_graph_uri: str
    ontology_snapshot_ref: str
    ontology_snapshot_hash: Optional[str] = None
    source_label: str = FactSource.SEMANTIC.value
    advisory_only: bool = True
    auto_answer_eligible: bool = True
    auto_answered: bool = False
    alters_deterministic_outcome: bool = False
    status: str = "available"
    abstain_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "factName": self.fact_name,
            "ontologyIri": self.ontology_iri,
            "relationship": self.relationship,
            "suggestedValue": self.suggested_value,
            "confidence": self.confidence,
            "basis": self.basis,
            "sourceGraphUri": self.source_graph_uri,
            "ontologySnapshotRef": self.ontology_snapshot_ref,
            "ontologySnapshotHash": self.ontology_snapshot_hash,
            "sourceLabel": self.source_label,
            "advisoryOnly": self.advisory_only,
            "autoAnswerEligible": self.auto_answer_eligible,
            "autoAnswered": self.auto_answered,
            "altersDeterministicOutcome": self.alters_deterministic_outcome,
            "status": self.status,
            "abstainReason": self.abstain_reason,
        }


class OntologyBindingResolver:
    """Resolve fact names to ontology IRIs with deterministic exact-label matching."""

    def resolve(
        self,
        fact_names: Iterable[str],
        ontology_triples: Iterable[OntologyTriple],
        *,
        source_graph_uri: str = "in_memory_triples",
    ) -> OntologyBindingReport:
        index = OntologyIndex(tuple(ontology_triples))
        labels = index.label_index()
        bindings: List[OntologyBindingEvidence] = []
        ambiguous: List[OntologyBindingIssue] = []
        missing: List[OntologyBindingIssue] = []

        for fact_name in sorted({str(name) for name in fact_names if str(name).strip()}):
            key = _normalise_label(fact_name)
            candidates = tuple(sorted(labels.get(key, ())))
            if len(candidates) == 1:
                subject = candidates[0]
                matched_predicate, matched_label = index.best_label_for(subject)
                bindings.append(
                    OntologyBindingEvidence(
                        fact_name=fact_name,
                        ontology_iri=subject,
                        matched_label=matched_label,
                        matched_predicate=matched_predicate,
                        source_graph_uri=source_graph_uri,
                    )
                )
            elif len(candidates) > 1:
                ambiguous.append(
                    OntologyBindingIssue(
                        fact_name=fact_name,
                        status="ambiguous",
                        candidates=candidates,
                    )
                )
            else:
                missing.append(
                    OntologyBindingIssue(
                        fact_name=fact_name,
                        status="missing",
                    )
                )

        return OntologyBindingReport(
            bindings=tuple(bindings),
            ambiguous=tuple(ambiguous),
            missing=tuple(missing),
        )


@dataclass(frozen=True)
class SemanticReceiptContext:
    receipt_id: str
    generated_at: str
    session_id: str
    rule_name: str
    target_node_name: str
    outcome_code: str = "REVIEW"
    outcome_status: str = "PENDING"
    reasoning_mode: str = "DEDUCTION"
    confidence: float = 1.0
    rule_version: str = "local-fixture-v0"


@dataclass(frozen=True)
class SemanticTag:
    fact_name: str
    semantic_fact_name: str
    asserted_value: Any
    tag_iri: str
    relationship: str
    source_label: str
    provenance: Dict[str, str]


@dataclass(frozen=True)
class SemanticHypothesis:
    fact_name: str
    suggested_value: Any
    basis: str
    confidence: float = 0.0
    confirmation_status: str = "unconfirmed"
    source_label: str = FactSource.HYPOTHETICAL.value


@dataclass(frozen=True)
class OntologyDiscoveredCandidate:
    fact_name: str
    suggested_value: Any
    basis: str
    ontology_iri: str
    candidate_type: str = "hypothesis"
    approval_state: str = "candidate"
    source_label: str = FactSource.SEMANTIC.value
    requires_rule_approval: bool = True
    alters_deterministic_outcome: bool = False


@dataclass(frozen=True)
class SemanticEnrichmentResult:
    semantic_tags: Tuple[SemanticTag, ...]
    receipt: Dict[str, Any]


class SemanticFactEnricher:
    """Adds ontology-derived tags without mutating authoritative fact layers."""

    def enrich(
        self,
        fact_store: FactStorePort,
        bindings: Iterable[BoundFact],
        ontology_triples: Iterable[OntologyTriple],
        *,
        context: SemanticReceiptContext,
        ontology_snapshot_ref: str,
        hypotheses: Iterable[SemanticHypothesis] = (),
        ontology_discovered_candidates: Iterable[OntologyDiscoveredCandidate] = (),
        unsupported_ontology_constructs: Iterable[str] = (),
    ) -> SemanticEnrichmentResult:
        triples = tuple(ontology_triples)
        index = OntologyIndex(triples)
        tags: List[SemanticTag] = []

        for binding in bindings:
            asserted = fact_store.peek_in_layer(binding.fact_name, FactSource.ASSERTED)
            if asserted is None:
                continue
            for tag in self._derive_tags(binding, asserted.get_value(), index):
                tags.append(tag)

        for fact_name, fact_tags in _group_tags_by_fact(tags).items():
            semantic_fact_name = _semantic_tag_fact_name(fact_name)
            fact_store.set_fact(
                semantic_fact_name,
                FactValue([_semantic_tag_payload(tag) for tag in fact_tags]),
                source=FactSource.SEMANTIC,
            )

        receipt = _build_receipt(
            fact_store,
            tags,
            context=context,
            ontology_snapshot_ref=ontology_snapshot_ref,
            hypotheses=tuple(hypotheses),
            ontology_discovered_candidates=tuple(ontology_discovered_candidates),
            unsupported_ontology_constructs=tuple(unsupported_ontology_constructs),
        )
        return SemanticEnrichmentResult(semantic_tags=tuple(tags), receipt=receipt)

    def _derive_tags(
        self,
        binding: BoundFact,
        asserted_value: Any,
        index: "OntologyIndex",
    ) -> List[SemanticTag]:
        tags: List[SemanticTag] = []
        seen: set[Tuple[str, str]] = set()

        for class_iri in index.objects(binding.object_iri, RDF_TYPE):
            _append_tag(
                tags,
                self._tag(
                    binding,
                    asserted_value,
                    class_iri,
                    "rdf:type",
                    (binding.object_iri, RDF_TYPE, class_iri),
                    seen,
                ),
            )
            for ancestor, basis in index.class_ancestors(class_iri):
                _append_tag(
                    tags,
                    self._tag(
                        binding,
                        asserted_value,
                        ancestor,
                        basis[1],
                        basis,
                        seen,
                    ),
                )

        for property_iri, basis in index.property_lineage(binding.predicate_iri):
            for range_iri in index.objects(property_iri, RDFS_RANGE):
                _append_tag(
                    tags,
                    self._tag(
                        binding,
                        asserted_value,
                        range_iri,
                        "rdfs:range",
                        (property_iri, RDFS_RANGE, range_iri),
                        seen,
                    ),
                )
            for domain_iri in index.objects(property_iri, RDFS_DOMAIN):
                _append_tag(
                    tags,
                    self._tag(
                        binding,
                        asserted_value,
                        domain_iri,
                        "rdfs:domain",
                        (property_iri, RDFS_DOMAIN, domain_iri),
                        seen,
                    ),
                )
            if basis[1] == RDFS_SUBPROPERTY_OF:
                _append_tag(
                    tags,
                    self._tag(
                        binding,
                        asserted_value,
                        property_iri,
                        "rdfs:subPropertyOf",
                        basis,
                        seen,
                    ),
                )

        return tags

    def _tag(
        self,
        binding: BoundFact,
        asserted_value: Any,
        tag_iri: str,
        relationship: str,
        basis: OntologyTriple,
        seen: set[Tuple[str, str]],
    ) -> SemanticTag | None:
        key = (tag_iri, relationship)
        if key in seen:
            return None
        seen.add(key)
        return SemanticTag(
            fact_name=binding.fact_name,
            semantic_fact_name=_semantic_tag_fact_name(binding.fact_name),
            asserted_value=asserted_value,
            tag_iri=tag_iri,
            relationship=_compact_relationship(relationship),
            source_label=FactSource.SEMANTIC.value,
            provenance={
                "subject": basis[0],
                "predicate": basis[1],
                "object": basis[2],
                "ontologySource": "in_memory_triples",
            },
        )


class OntologyIndex:
    """In-memory, deterministic ontology index for the supported RDF/RDFS subset."""

    def __init__(self, triples: Sequence[OntologyTriple]) -> None:
        self._triples = tuple((str(s), str(p), str(o)) for s, p, o in triples)
        self._spo: Dict[Tuple[str, str], List[str]] = {}
        for subject, predicate, obj in self._triples:
            self._spo.setdefault((subject, predicate), []).append(obj)

    def objects(self, subject: str, predicate: str) -> Tuple[str, ...]:
        return tuple(self._spo.get((subject, predicate), ()))

    def triples(self) -> Tuple[OntologyTriple, ...]:
        return self._triples

    def label_index(self) -> Dict[str, Tuple[str, ...]]:
        labels: Dict[str, set[str]] = {}
        for subject, predicate, obj in self._triples:
            if predicate not in (INF_NAME, RDFS_LABEL):
                continue
            key = _normalise_label(obj)
            if key:
                labels.setdefault(key, set()).add(subject)
        return {key: tuple(sorted(subjects)) for key, subjects in labels.items()}

    def subjects_for_label(self, label: Any) -> Tuple[str, ...]:
        return self.label_index().get(_normalise_label(str(label)), ())

    def labels_for_subject(self, subject: str) -> Tuple[str, ...]:
        labels: List[str] = []
        for predicate in (INF_NAME, RDFS_LABEL):
            for value in self.objects(subject, predicate):
                if value not in labels:
                    labels.append(value)
        return tuple(labels)

    def best_label_for(self, subject: str) -> Tuple[str, str]:
        for predicate in (INF_NAME, RDFS_LABEL):
            values = self.objects(subject, predicate)
            if values:
                return predicate, values[0]
        return INF_NAME, subject

    def confidence_for(self, subject: str, default: float = 1.0) -> float:
        return self._confidence_for(subject, default)

    def get_equivalent_classes(self, iri: str) -> Tuple[str, ...]:
        values = set(self.objects(iri, OWL_EQUIVALENT_CLASS))
        values.update(
            subject
            for subject, predicate, obj in self._triples
            if predicate == OWL_EQUIVALENT_CLASS and obj == iri
        )
        return tuple(sorted(values))

    def get_subclasses(self, iri: str) -> Tuple[str, ...]:
        return tuple(
            sorted(
                subject
                for subject, predicate, obj in self._triples
                if predicate == RDFS_SUBCLASS_OF and obj == iri
            )
        )

    def get_instances(self, iri: str) -> Tuple[str, ...]:
        return tuple(
            sorted(
                subject
                for subject, predicate, obj in self._triples
                if predicate == RDF_TYPE and obj == iri
            )
        )

    def semantic_suggestions_for(
        self,
        binding: OntologyBindingEvidence,
        *,
        ontology_snapshot_ref: str,
        ontology_snapshot_hash: Optional[str] = None,
    ) -> Tuple[SemanticSuggestion, ...]:
        suggestions: List[SemanticSuggestion] = []
        subject = binding.ontology_iri

        for item in self.objects(subject, INF_HAS_ITEM):
            suggestions.append(
                SemanticSuggestion(
                    fact_name=binding.fact_name,
                    ontology_iri=subject,
                    relationship="inf:hasItem",
                    suggested_value=item,
                    confidence=binding.confidence,
                    source_graph_uri=binding.source_graph_uri,
                    ontology_snapshot_ref=ontology_snapshot_ref,
                    ontology_snapshot_hash=ontology_snapshot_hash,
                )
            )

        for predicate, relationship in (
            (RDFS_RANGE, "rdfs:range"),
            (RDFS_DOMAIN, "rdfs:domain"),
            (INF_VALUE_TYPE, "inf:valueType"),
        ):
            for obj in self.objects(subject, predicate):
                suggestions.append(
                    SemanticSuggestion(
                        fact_name=binding.fact_name,
                        ontology_iri=obj,
                        relationship=relationship,
                        suggested_value=None,
                        confidence=binding.confidence,
                        source_graph_uri=binding.source_graph_uri,
                        ontology_snapshot_ref=ontology_snapshot_ref,
                        ontology_snapshot_hash=ontology_snapshot_hash,
                    )
                )

        return tuple(suggestions)

    def value_suggestions_for(
        self,
        binding: OntologyBindingEvidence,
        *,
        ontology_snapshot_ref: str,
        ontology_snapshot_hash: Optional[str] = None,
    ) -> Tuple[OntologyValueSuggestion, ...]:
        suggestions: List[OntologyValueSuggestion] = []
        subject = binding.ontology_iri
        confidence = self._confidence_for(subject, binding.confidence)

        defaults = tuple(dict.fromkeys(self.objects(subject, INF_DEFAULT_VALUE)))
        if len(defaults) == 1:
            suggestions.append(
                OntologyValueSuggestion(
                    fact_name=binding.fact_name,
                    ontology_iri=subject,
                    relationship="inf:defaultValue",
                    suggested_value=defaults[0],
                    confidence=confidence,
                    basis="explicit_default_value",
                    source_graph_uri=binding.source_graph_uri,
                    ontology_snapshot_ref=ontology_snapshot_ref,
                    ontology_snapshot_hash=ontology_snapshot_hash,
                )
            )
        elif len(defaults) > 1:
            suggestions.append(
                OntologyValueSuggestion(
                    fact_name=binding.fact_name,
                    ontology_iri=subject,
                    relationship="inf:defaultValue",
                    suggested_value=None,
                    confidence=0.0,
                    basis="contradictory_default_values",
                    source_graph_uri=binding.source_graph_uri,
                    ontology_snapshot_ref=ontology_snapshot_ref,
                    ontology_snapshot_hash=ontology_snapshot_hash,
                    auto_answer_eligible=False,
                    status="abstained",
                    abstain_reason="contradictory_default_values",
                )
            )

        enum_items = tuple(dict.fromkeys(self.objects(subject, INF_HAS_ITEM)))
        if not defaults and len(enum_items) == 1:
            suggestions.append(
                OntologyValueSuggestion(
                    fact_name=binding.fact_name,
                    ontology_iri=subject,
                    relationship="inf:hasItem",
                    suggested_value=enum_items[0],
                    confidence=min(confidence, 0.9),
                    basis="single_allowed_value",
                    source_graph_uri=binding.source_graph_uri,
                    ontology_snapshot_ref=ontology_snapshot_ref,
                    ontology_snapshot_hash=ontology_snapshot_hash,
                )
            )

        return tuple(suggestions)

    def constraint_suggestions_for(
        self,
        binding: OntologyBindingEvidence,
        *,
        ontology_snapshot_ref: str,
        ontology_snapshot_hash: Optional[str] = None,
    ) -> Tuple[SemanticSuggestion, ...]:
        suggestions: List[SemanticSuggestion] = []
        subject = binding.ontology_iri
        for predicate, relationship in (
            (RDFS_RANGE, "rdfs:range"),
            (RDFS_DOMAIN, "rdfs:domain"),
            (INF_VALUE_TYPE, "inf:valueType"),
            (INF_MINIMUM, "inf:minimum"),
            (INF_MAXIMUM, "inf:maximum"),
        ):
            for obj in self.objects(subject, predicate):
                suggestions.append(
                    SemanticSuggestion(
                        fact_name=binding.fact_name,
                        ontology_iri=subject,
                        relationship=relationship,
                        suggested_value=obj,
                        confidence=binding.confidence,
                        source_graph_uri=binding.source_graph_uri,
                        ontology_snapshot_ref=ontology_snapshot_ref,
                        ontology_snapshot_hash=ontology_snapshot_hash,
                    )
                )
        return tuple(suggestions)

    def _confidence_for(self, subject: str, default: float) -> float:
        values = self.objects(subject, INF_CONFIDENCE)
        if not values:
            return default
        try:
            return float(values[0])
        except (TypeError, ValueError):
            return default

    def class_ancestors(self, class_iri: str) -> Tuple[Tuple[str, OntologyTriple], ...]:
        return self._closure(
            class_iri,
            (
                (RDFS_SUBCLASS_OF, False),
                (OWL_EQUIVALENT_CLASS, True),
            ),
        )

    def property_lineage(
        self, property_iri: str
    ) -> Tuple[Tuple[str, OntologyTriple], ...]:
        lineage = [(property_iri, (property_iri, "", property_iri))]
        lineage.extend(self._closure(property_iri, ((RDFS_SUBPROPERTY_OF, False),)))
        return tuple(lineage)

    def _closure(
        self,
        start: str,
        predicates: Sequence[Tuple[str, bool]],
    ) -> List[Tuple[str, OntologyTriple]]:
        queue = [start]
        visited = {start}
        results: List[Tuple[str, OntologyTriple]] = []

        while queue:
            current = queue.pop(0)
            for predicate, bidirectional in predicates:
                for target in self.objects(current, predicate):
                    if target not in visited:
                        visited.add(target)
                        basis = (current, predicate, target)
                        results.append((target, basis))
                        queue.append(target)
                if not bidirectional:
                    continue
                for subject, found_predicate, obj in self._triples:
                    if found_predicate == predicate and obj == current and subject not in visited:
                        visited.add(subject)
                        basis = (subject, predicate, current)
                        results.append((subject, basis))
                        queue.append(subject)
        return results


_OntologyIndex = OntologyIndex


def build_semantic_suggestions(
    fact_names: Iterable[str],
    ontology_triples: Iterable[OntologyTriple],
    *,
    source_graph_uri: str = "in_memory_triples",
    ontology_snapshot_ref: str,
    ontology_snapshot_hash: Optional[str] = None,
) -> Tuple[OntologyBindingReport, Dict[str, Tuple[SemanticSuggestion, ...]]]:
    """Resolve bindings and build response-only advisory suggestions."""
    triples = tuple(ontology_triples)
    index = OntologyIndex(triples)
    report = OntologyBindingResolver().resolve(
        fact_names,
        triples,
        source_graph_uri=source_graph_uri,
    )
    suggestions = {
        binding.fact_name: index.semantic_suggestions_for(
            binding,
            ontology_snapshot_ref=ontology_snapshot_ref,
            ontology_snapshot_hash=ontology_snapshot_hash,
        )
        for binding in report.bindings
    }
    return report, suggestions


def build_ontology_value_suggestions(
    report: OntologyBindingReport,
    ontology_triples: Iterable[OntologyTriple],
    *,
    ontology_snapshot_ref: str,
    ontology_snapshot_hash: Optional[str] = None,
) -> Dict[str, Tuple[OntologyValueSuggestion, ...]]:
    """Build default-value candidates from already-resolved ontology bindings."""
    index = OntologyIndex(tuple(ontology_triples))
    return {
        binding.fact_name: index.value_suggestions_for(
            binding,
            ontology_snapshot_ref=ontology_snapshot_ref,
            ontology_snapshot_hash=ontology_snapshot_hash,
        )
        for binding in report.bindings
    }


def build_ontology_constraint_suggestions(
    report: OntologyBindingReport,
    ontology_triples: Iterable[OntologyTriple],
    *,
    ontology_snapshot_ref: str,
    ontology_snapshot_hash: Optional[str] = None,
) -> Dict[str, Tuple[SemanticSuggestion, ...]]:
    """Build range/domain/type advisory payloads without fact-store writes."""
    index = OntologyIndex(tuple(ontology_triples))
    return {
        binding.fact_name: index.constraint_suggestions_for(
            binding,
            ontology_snapshot_ref=ontology_snapshot_ref,
            ontology_snapshot_hash=ontology_snapshot_hash,
        )
        for binding in report.bindings
    }


def _build_receipt(
    fact_store: FactStorePort,
    semantic_tags: Sequence[SemanticTag],
    *,
    context: SemanticReceiptContext,
    ontology_snapshot_ref: str,
    hypotheses: Sequence[SemanticHypothesis],
    ontology_discovered_candidates: Sequence[OntologyDiscoveredCandidate],
    unsupported_ontology_constructs: Sequence[str],
) -> Dict[str, Any]:
    asserted = _facts_for_source(fact_store, FactSource.ASSERTED)
    inferred = _facts_for_source(fact_store, FactSource.INFERRED)
    inferred.extend(_facts_for_source(fact_store, FactSource.LEARNED))
    hypothesis_payload = [_hypothesis_payload(item) for item in hypotheses]
    candidate_payload = [
        _ontology_candidate_payload(item)
        for item in ontology_discovered_candidates
    ]
    semantic_payload = [_semantic_tag_payload(item) for item in semantic_tags]

    return {
        "schemaVersion": "inferra.receipt.v0",
        "receiptId": context.receipt_id,
        "generatedAt": context.generated_at,
        "environment": {"dataClass": "synthetic", "production": False},
        "execution": {
            "sessionId": context.session_id,
            "ruleName": context.rule_name,
            "targetNodeName": context.target_node_name,
            "reasoningMode": context.reasoning_mode,
            "confidence": context.confidence,
        },
        "outcome": {
            "code": context.outcome_code,
            "sourceNode": context.target_node_name,
            "status": context.outcome_status,
            "explanation": (
                "Ontology-derived semantic tags and candidates are advisory only."
            ),
        },
        "ruleBasis": {
            "ruleName": context.rule_name,
            "ruleVersion": context.rule_version,
            "imports": [],
            "unsupportedOntologyConstructs": list(unsupported_ontology_constructs),
        },
        "assertedFacts": asserted,
        "inferredFacts": inferred,
        "semanticTags": semantic_payload,
        "hypotheses": hypothesis_payload,
        "ontologyDiscoveredCandidates": candidate_payload,
        "sourceLabels": {
            "ASSERTED": "Supplied or authoritative input",
            "INFERRED": "Derived by deterministic rule execution",
            "LEARNED": "Derived from learned or inductive evidence",
            "HYPOTHETICAL": "Abductive suggestion requiring confirmation",
            "SEMANTIC": "Ontology-derived tag or enrichment",
        },
        "missingEvidence": [
            {
                "name": item.fact_name,
                "status": item.confirmation_status,
                "sourceLabel": item.source_label,
            }
            for item in hypotheses
        ],
        "trace": {
            "traceId": context.session_id,
            "provO": {
                "format": "json",
                "value": {
                    "provenanceEvents": _provenance_events(
                        asserted,
                        inferred,
                        semantic_payload,
                        hypothesis_payload,
                        candidate_payload,
                    )
                },
            },
            "convergenceTrace": [
                "DETERMINISTIC_OUTCOME_PRESERVED",
                "SEMANTIC_TAGS_WRITTEN_TO_SEMANTIC_LAYER",
                "ONTOLOGY_CANDIDATES_REQUIRE_RULE_APPROVAL",
            ],
            "provenanceLink": None,
            "externalReasonerCalls": False,
        },
        "replayInputs": {
            "ruleName": context.rule_name,
            "targetNodeName": context.target_node_name,
            "answers": [],
            "ontologySnapshotRef": ontology_snapshot_ref,
        },
        "disclaimers": [
            "Synthetic non-production proof data only.",
            "OWL 2 RL-aligned subset only; no full OWL 2 RL compliance claim.",
            "No CMS, HIPAA, payer, medical, legal, regulator, or production-readiness claim.",
            "Ontology-derived and hypothetical values do not override asserted evidence.",
        ],
        "signing": {"status": "not_supported"},
    }


def _facts_for_source(
    fact_store: FactStorePort,
    source: FactSource,
) -> List[Dict[str, Any]]:
    return [
        {
            "name": name,
            "value": value.get_value(),
            "valueType": value.get_value_type().value,
            "sourceLabel": source.value,
        }
        for name, value in sorted(fact_store.get_layer_snapshot(source).items())
    ]


def _provenance_events(
    asserted: Sequence[Dict[str, Any]],
    inferred: Sequence[Dict[str, Any]],
    semantic_tags: Sequence[Dict[str, Any]],
    hypotheses: Sequence[Dict[str, Any]],
    ontology_discovered_candidates: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    events.extend(
        {
            "kind": "asserted_fact",
            "factName": fact["name"],
            "sourceLabel": FactSource.ASSERTED.value,
        }
        for fact in asserted
    )
    events.extend(
        {
            "kind": "inferred_fact",
            "factName": fact["name"],
            "sourceLabel": fact["sourceLabel"],
        }
        for fact in inferred
    )
    events.extend(
        {
            "kind": "semantic_tag",
            "factName": tag["factName"],
            "semanticFactName": tag["semanticFactName"],
            "sourceLabel": FactSource.SEMANTIC.value,
            "relationship": tag["relationship"],
        }
        for tag in semantic_tags
    )
    events.extend(
        {
            "kind": "hypothesis",
            "factName": item["factName"],
            "sourceLabel": FactSource.HYPOTHETICAL.value,
            "confirmationStatus": item["confirmationStatus"],
        }
        for item in hypotheses
    )
    events.extend(
        {
            "kind": "ontology_discovered_candidate",
            "factName": item["factName"],
            "sourceLabel": FactSource.SEMANTIC.value,
            "approvalState": item["approvalState"],
        }
        for item in ontology_discovered_candidates
    )
    return events


def _group_tags_by_fact(
    tags: Sequence[SemanticTag],
) -> Dict[str, List[SemanticTag]]:
    grouped: Dict[str, List[SemanticTag]] = {}
    for tag in tags:
        grouped.setdefault(tag.fact_name, []).append(tag)
    return grouped


def _semantic_tag_fact_name(fact_name: str) -> str:
    return f"{fact_name}__semantic_tags"


def _normalise_label(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def _append_tag(tags: List[SemanticTag], tag: SemanticTag | None) -> None:
    if tag is not None:
        tags.append(tag)


def _semantic_tag_payload(tag: SemanticTag) -> Dict[str, Any]:
    return {
        "factName": tag.fact_name,
        "semanticFactName": tag.semantic_fact_name,
        "assertedValue": tag.asserted_value,
        "tagIri": tag.tag_iri,
        "relationship": tag.relationship,
        "sourceLabel": tag.source_label,
        "provenance": dict(tag.provenance),
    }


def _hypothesis_payload(hypothesis: SemanticHypothesis) -> Dict[str, Any]:
    return {
        "factName": hypothesis.fact_name,
        "suggestedValue": hypothesis.suggested_value,
        "basis": hypothesis.basis,
        "confidence": hypothesis.confidence,
        "confirmationStatus": hypothesis.confirmation_status,
        "sourceLabel": hypothesis.source_label,
    }


def _ontology_candidate_payload(
    candidate: OntologyDiscoveredCandidate,
) -> Dict[str, Any]:
    return {
        "factName": candidate.fact_name,
        "suggestedValue": candidate.suggested_value,
        "basis": candidate.basis,
        "ontologyIri": candidate.ontology_iri,
        "candidateType": candidate.candidate_type,
        "approvalState": candidate.approval_state,
        "sourceLabel": candidate.source_label,
        "requiresRuleApproval": candidate.requires_rule_approval,
        "altersDeterministicOutcome": candidate.alters_deterministic_outcome,
    }


def _compact_relationship(predicate: str) -> str:
    mapping = {
        RDF_TYPE: "rdf:type",
        RDFS_SUBCLASS_OF: "rdfs:subClassOf",
        RDFS_SUBPROPERTY_OF: "rdfs:subPropertyOf",
        RDFS_DOMAIN: "rdfs:domain",
        RDFS_RANGE: "rdfs:range",
        RDFS_LABEL: "rdfs:label",
        OWL_EQUIVALENT_CLASS: "owl:equivalentClass",
        INF_NAME: "inf:name",
        INF_HAS_ITEM: "inf:hasItem",
        INF_VALUE_TYPE: "inf:valueType",
        INF_DEFAULT_VALUE: "inf:defaultValue",
        INF_CONFIDENCE: "inf:confidence",
        INF_MINIMUM: "inf:minimum",
        INF_MAXIMUM: "inf:maximum",
    }
    return mapping.get(predicate, predicate)
