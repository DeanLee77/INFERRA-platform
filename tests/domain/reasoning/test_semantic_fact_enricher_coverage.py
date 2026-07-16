"""Focused branch coverage for semantic fact enrichment."""

from src.domain.reasoning.semantic_fact_enricher import (
    INF_CONFIDENCE,
    INF_MINIMUM,
    INF_NAME,
    OWL_EQUIVALENT_CLASS,
    RDF_TYPE,
    RDFS_DOMAIN,
    RDFS_RANGE,
    BoundFact,
    OntologyBindingEvidence,
    OntologyBindingReport,
    OntologyIndex,
    SemanticFactEnricher,
    SemanticReceiptContext,
)
from src.domain.state import LayeredFactStore


def _binding_evidence(subject: str = "urn:ontology:claim") -> OntologyBindingEvidence:
    return OntologyBindingEvidence(
        fact_name="claim status",
        ontology_iri=subject,
        matched_label="claim status",
        matched_predicate=INF_NAME,
        source_graph_uri="urn:graph:test",
    )


def test_binding_report_indexes_evidence_by_fact_name() -> None:
    evidence = _binding_evidence()
    report = OntologyBindingReport(
        bindings=(evidence,),
        ambiguous=(),
        missing=(),
    )

    assert report.binding_by_fact() == {"claim status": evidence}


def test_enrichment_skips_bindings_without_asserted_facts() -> None:
    result = SemanticFactEnricher().enrich(
        LayeredFactStore(),
        bindings=[
            BoundFact(
                fact_name="missing fact",
                subject_iri="urn:subject:claim",
                predicate_iri="urn:predicate:status",
                object_iri="urn:object:status",
            )
        ],
        ontology_triples=[],
        context=SemanticReceiptContext(
            receipt_id="receipt-missing-fact",
            generated_at="2026-07-16T00:00:00Z",
            session_id="session-missing-fact",
            rule_name="coverage_rule",
            target_node_name="decision",
        ),
        ontology_snapshot_ref="urn:snapshot:test",
    )

    assert result.semantic_tags == ()


def test_domain_tags_are_emitted_and_duplicate_type_tags_are_deduplicated() -> None:
    binding = BoundFact(
        fact_name="claim status",
        subject_iri="urn:subject:claim",
        predicate_iri="urn:predicate:status",
        object_iri="urn:object:status",
    )
    index = OntologyIndex(
        [
            (binding.object_iri, RDF_TYPE, "urn:class:Status"),
            (binding.object_iri, RDF_TYPE, "urn:class:Status"),
            (binding.predicate_iri, RDFS_DOMAIN, "urn:class:Claim"),
        ]
    )

    tags = SemanticFactEnricher()._derive_tags(binding, "open", index)

    assert [(tag.tag_iri, tag.relationship) for tag in tags] == [
        ("urn:class:Status", "rdf:type"),
        ("urn:class:Claim", "rdfs:domain"),
    ]


def test_index_fallbacks_constraints_and_reverse_equivalence() -> None:
    subject = "urn:ontology:claim"
    equivalent = "urn:ontology:equivalent-claim"
    index = OntologyIndex(
        [
            (subject, RDFS_RANGE, "urn:type:ClaimStatus"),
            (subject, INF_MINIMUM, "1"),
            (subject, INF_CONFIDENCE, "not-a-number"),
            (equivalent, OWL_EQUIVALENT_CLASS, subject),
        ]
    )
    evidence = _binding_evidence(subject)

    assert index.best_label_for(subject) == (INF_NAME, subject)
    assert index.confidence_for(subject, default=0.25) == 0.25

    semantic = index.semantic_suggestions_for(
        evidence,
        ontology_snapshot_ref="urn:snapshot:test",
    )
    constraints = index.constraint_suggestions_for(
        evidence,
        ontology_snapshot_ref="urn:snapshot:test",
    )
    ancestors = index.class_ancestors(subject)

    assert [(item.relationship, item.ontology_iri) for item in semantic] == [
        ("rdfs:range", "urn:type:ClaimStatus")
    ]
    assert {item.relationship for item in constraints} == {
        "rdfs:range",
        "inf:minimum",
    }
    assert ancestors == [
        (
            equivalent,
            (equivalent, OWL_EQUIVALENT_CLASS, subject),
        ),
    ]
