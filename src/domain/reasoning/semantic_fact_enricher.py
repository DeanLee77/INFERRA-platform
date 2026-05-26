"""Semantic fact enrichment over an in-memory OWL/RDFS-aligned subset."""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from src.domain.fact_values import FactValue
from src.domain.state.fact_source import FactSource
from src.ports.fact_store_port import FactStorePort

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_SUBCLASS_OF = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
RDFS_SUBPROPERTY_OF = "http://www.w3.org/2000/01/rdf-schema#subPropertyOf"
RDFS_DOMAIN = "http://www.w3.org/2000/01/rdf-schema#domain"
RDFS_RANGE = "http://www.w3.org/2000/01/rdf-schema#range"
OWL_EQUIVALENT_CLASS = "http://www.w3.org/2002/07/owl#equivalentClass"

OntologyTriple = Tuple[str, str, str]


@dataclass(frozen=True)
class BoundFact:
    """Binds an asserted fact to the RDF statement that describes it."""

    fact_name: str
    subject_iri: str
    predicate_iri: str
    object_iri: str


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
        index = _OntologyIndex(triples)
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
        index: "_OntologyIndex",
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


class _OntologyIndex:
    def __init__(self, triples: Sequence[OntologyTriple]) -> None:
        self._triples = tuple((str(s), str(p), str(o)) for s, p, o in triples)
        self._spo: Dict[Tuple[str, str], List[str]] = {}
        for subject, predicate, obj in self._triples:
            self._spo.setdefault((subject, predicate), []).append(obj)

    def objects(self, subject: str, predicate: str) -> Tuple[str, ...]:
        return tuple(self._spo.get((subject, predicate), ()))

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
        OWL_EQUIVALENT_CLASS: "owl:equivalentClass",
    }
    return mapping.get(predicate, predicate)
