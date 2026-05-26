from src.domain.fact_values import FactValue
from src.domain.reasoning.semantic_fact_enricher import (
    BoundFact,
    OntologyDiscoveredCandidate,
    RDF_TYPE,
    RDFS_RANGE,
    RDFS_SUBCLASS_OF,
    RDFS_SUBPROPERTY_OF,
    SemanticFactEnricher,
    SemanticHypothesis,
    SemanticReceiptContext,
)
from src.domain.state import FactSource, LayeredFactStore

INF = "http://inferra.ai/schema#"
SYN = "http://inferra.ai/synthetic#"


def test_semantic_fact_enricher_receipt_keeps_ontology_advisory():
    store = LayeredFactStore()
    store.set_fact("requested_service", FactValue("power_wheelchair"), FactSource.ASSERTED)
    store.set_fact("authorization_outcome", FactValue("REVIEW"), FactSource.INFERRED)

    result = SemanticFactEnricher().enrich(
        store,
        bindings=[
            BoundFact(
                fact_name="requested_service",
                subject_iri=f"{SYN}request/001",
                predicate_iri=f"{INF}requestedService",
                object_iri=f"{SYN}power_wheelchair_request",
            )
        ],
        ontology_triples=[
            (
                f"{SYN}power_wheelchair_request",
                RDF_TYPE,
                f"{INF}PowerWheelchairRequest",
            ),
            (
                f"{INF}PowerWheelchairRequest",
                RDFS_SUBCLASS_OF,
                f"{INF}DurableMedicalEquipmentRequest",
            ),
            (f"{INF}requestedService", RDFS_RANGE, f"{INF}PriorAuthServiceRequest"),
            (
                f"{INF}requestedService",
                RDFS_SUBPROPERTY_OF,
                f"{INF}requestedIntervention",
            ),
            (f"{INF}requestedIntervention", RDFS_RANGE, f"{INF}CareIntervention"),
        ],
        context=SemanticReceiptContext(
            receipt_id="synthetic-pa-semantic-001",
            generated_at="2026-05-26T00:00:00Z",
            session_id="synthetic-session-001",
            rule_name="synthetic_prior_auth_v0",
            target_node_name="authorization_outcome",
        ),
        ontology_snapshot_ref="synthetic-pa-ontology-v0",
        hypotheses=[
            SemanticHypothesis(
                fact_name="face_to_face_exam_documented",
                suggested_value=True,
                basis="DME ontology suggests documentation evidence for review.",
                confidence=0.4,
            )
        ],
        ontology_discovered_candidates=[
            OntologyDiscoveredCandidate(
                fact_name="face_to_face_exam_documented",
                suggested_value=True,
                basis="Derived from DME request class tags.",
                ontology_iri=f"{INF}DurableMedicalEquipmentRequest",
            )
        ],
    )

    asserted = store.peek_in_layer("requested_service", FactSource.ASSERTED)
    semantic_tags = store.peek_in_layer(
        "requested_service__semantic_tags",
        FactSource.SEMANTIC,
    )

    assert asserted.get_value() == "power_wheelchair"
    assert store.get_unified_view()["requested_service"].get_value() == "power_wheelchair"
    assert semantic_tags is not None
    assert "requested_service" not in store.get_overrides()

    tag_pairs = {
        (tag.tag_iri, tag.relationship)
        for tag in result.semantic_tags
    }
    assert (f"{INF}PowerWheelchairRequest", "rdf:type") in tag_pairs
    assert (f"{INF}DurableMedicalEquipmentRequest", "rdfs:subClassOf") in tag_pairs
    assert (f"{INF}PriorAuthServiceRequest", "rdfs:range") in tag_pairs
    assert (f"{INF}CareIntervention", "rdfs:range") in tag_pairs

    receipt = result.receipt
    assert receipt["outcome"]["code"] == "REVIEW"
    assert receipt["trace"]["externalReasonerCalls"] is False
    assert receipt["assertedFacts"] == [
        {
            "name": "requested_service",
            "value": "power_wheelchair",
            "valueType": "STRING",
            "sourceLabel": "ASSERTED",
        }
    ]
    assert receipt["inferredFacts"] == [
        {
            "name": "authorization_outcome",
            "value": "REVIEW",
            "valueType": "STRING",
            "sourceLabel": "INFERRED",
        }
    ]
    assert receipt["semanticTags"][0]["sourceLabel"] == "SEMANTIC"
    assert receipt["hypotheses"][0]["sourceLabel"] == "HYPOTHETICAL"
    assert receipt["hypotheses"][0]["confidence"] == 0.4
    assert receipt["ontologyDiscoveredCandidates"][0]["approvalState"] == "candidate"
    assert receipt["ontologyDiscoveredCandidates"][0]["requiresRuleApproval"] is True
    assert receipt["ontologyDiscoveredCandidates"][0]["altersDeterministicOutcome"] is False
    assert store.peek_in_layer("face_to_face_exam_documented", FactSource.INFERRED) is None
    assert store.peek_in_layer("face_to_face_exam_documented", FactSource.ASSERTED) is None

    event_kinds = {
        event["kind"]
        for event in receipt["trace"]["provO"]["value"]["provenanceEvents"]
    }
    assert {
        "asserted_fact",
        "inferred_fact",
        "semantic_tag",
        "hypothesis",
        "ontology_discovered_candidate",
    }.issubset(event_kinds)
