from src.domain.fact_values import FactValue
from src.domain.reasoning.ontology_reasoner import OntologyReasoner
from src.domain.reasoning.semantic_fact_enricher import (
    INF_CONFIDENCE,
    INF_NAME,
    OWL_EQUIVALENT_CLASS,
    RDF_TYPE,
    RDFS_SUBCLASS_OF,
    OntologyIndex,
)
from src.domain.state import FactSource, LayeredFactStore


INF = "http://inferra.ai/schema#"
SYN = "http://inferra.ai/synthetic#"


def _reasoner(**kwargs):
    return OntologyReasoner(
        source_graph_uri="urn:graph",
        ontology_snapshot_ref="rule:hash",
        ontology_snapshot_hash="hash",
        confidence_threshold=kwargs.pop("confidence_threshold", 0.85),
        max_closure_depth=kwargs.pop("max_closure_depth", 10),
        **kwargs,
    )


def test_materialize_derives_subclass_fact_with_trace_payload():
    index = OntologyIndex(
        [
            (f"{SYN}forklift", INF_NAME, "forklift"),
            (f"{SYN}forklift", RDF_TYPE, f"{INF}IndustrialVehicle"),
            (f"{INF}IndustrialVehicle", RDFS_SUBCLASS_OF, f"{INF}TypeApprovedEquipment"),
            (f"{INF}TypeApprovedEquipment", INF_NAME, "vehicle is type approved"),
            (f"{INF}TypeApprovedEquipment", INF_CONFIDENCE, "0.95"),
        ]
    )

    result = _reasoner().materialize(
        "vehicle classification",
        FactValue("forklift"),
        index,
    )

    assert [item.fact_name for item in result.derived_facts] == [
        "vehicle is type approved"
    ]
    derived = result.derived_facts[0]
    assert derived.fact_value.get_value() is True
    assert derived.confidence == 0.95
    trace = next(item for item in result.trace if item["status"] == "materialized")
    assert trace["status"] == "materialized"
    assert trace["sourceGraphUri"] == "urn:graph"
    assert trace["ontologySnapshotHash"] == "hash"
    assert trace["factSource"] == "INFERRED"
    assert trace["materializedInference"] is True
    assert trace["derivationRule"] == "rdfs_subclass_closure"
    assert f"{INF}TypeApprovedEquipment" in trace["derivationPath"]
    assert trace["missingPrerequisites"] == ["forklift"]
    assert trace["expectedInformationGain"] == 0


def test_materialize_abstains_on_ambiguous_value_binding():
    index = OntologyIndex(
        [
            (f"{SYN}forklift-a", INF_NAME, "forklift"),
            (f"{SYN}forklift-b", INF_NAME, "forklift"),
        ]
    )

    result = _reasoner().materialize(
        "vehicle classification",
        FactValue("forklift"),
        index,
    )

    assert result.derived_facts == ()
    assert result.trace[0]["status"] == "abstained"
    assert result.trace[0]["abstentionCause"] == "ambiguous_value_binding"
    assert result.trace[0]["missingPrerequisites"] == []
    assert result.trace[0]["expectedInformationGain"] == 0
    assert set(result.trace[0]["candidateIris"]) == {
        f"{SYN}forklift-a",
        f"{SYN}forklift-b",
    }


def test_materialize_never_overwrites_asserted_conflict():
    index = OntologyIndex(
        [
            (f"{SYN}forklift", INF_NAME, "forklift"),
            (f"{SYN}forklift", RDF_TYPE, f"{INF}IndustrialVehicle"),
            (f"{INF}IndustrialVehicle", RDFS_SUBCLASS_OF, f"{INF}TypeApprovedEquipment"),
            (f"{INF}TypeApprovedEquipment", INF_NAME, "vehicle is type approved"),
            (f"{INF}TypeApprovedEquipment", INF_CONFIDENCE, "0.95"),
        ]
    )
    store = LayeredFactStore()
    store.set_fact("vehicle is type approved", FactValue(False), FactSource.ASSERTED)

    result = _reasoner().materialize(
        "vehicle classification",
        FactValue("forklift"),
        index,
        fact_store=store,
    )

    assert result.derived_facts == ()
    assert store.peek_in_layer(
        "vehicle is type approved",
        FactSource.ASSERTED,
    ).get_value() is False
    conflict = next(
        item for item in result.trace
        if item["abstentionCause"] == "asserted_fact_conflict"
    )
    assert conflict["contradictionCause"] == "asserted_fact_conflict"


def test_materialize_can_promote_when_only_semantic_fact_exists():
    index = OntologyIndex(
        [
            (f"{SYN}forklift", INF_NAME, "forklift"),
            (f"{SYN}forklift", RDF_TYPE, f"{INF}IndustrialVehicle"),
            (f"{INF}IndustrialVehicle", RDFS_SUBCLASS_OF, f"{INF}TypeApprovedEquipment"),
            (f"{INF}TypeApprovedEquipment", INF_NAME, "vehicle is type approved"),
            (f"{INF}TypeApprovedEquipment", INF_CONFIDENCE, "0.95"),
        ]
    )
    store = LayeredFactStore()
    store.set_fact(
        "vehicle is type approved",
        FactValue({"advisory": True}),
        FactSource.SEMANTIC,
    )

    result = _reasoner().materialize(
        "vehicle classification",
        FactValue("forklift"),
        index,
        fact_store=store,
    )

    assert [item.fact_name for item in result.derived_facts] == [
        "vehicle is type approved"
    ]


def test_materialize_abstains_on_stale_or_unversioned_snapshot():
    index = OntologyIndex([(f"{SYN}forklift", INF_NAME, "forklift")])
    reasoner = OntologyReasoner(
        source_graph_uri="urn:graph",
        ontology_snapshot_ref="rule:missing",
        ontology_snapshot_hash=None,
    )

    result = reasoner.materialize(
        "vehicle classification",
        FactValue("forklift"),
        index,
    )

    assert result.derived_facts == ()
    assert result.trace[0]["abstentionCause"] == (
        "stale_or_unversioned_ontology_snapshot"
    )


def test_materialize_is_deterministic_and_does_not_mutate_triples():
    triples = [
        (f"{SYN}forklift", INF_NAME, "forklift"),
        (f"{SYN}forklift", RDF_TYPE, f"{INF}IndustrialVehicle"),
        (f"{INF}IndustrialVehicle", RDFS_SUBCLASS_OF, f"{INF}TypeApprovedEquipment"),
        (f"{INF}TypeApprovedEquipment", INF_NAME, "vehicle is type approved"),
        (f"{INF}TypeApprovedEquipment", INF_CONFIDENCE, "0.95"),
    ]
    index = OntologyIndex(triples)
    before = index.triples()
    reasoner = _reasoner()

    first = reasoner.materialize("vehicle classification", FactValue("forklift"), index)
    second = reasoner.materialize("vehicle classification", FactValue("forklift"), index)

    assert first.trace == second.trace
    assert index.triples() == before


def test_materialize_supports_equivalent_class_closure():
    index = OntologyIndex(
        [
            (f"{SYN}forklift", INF_NAME, "forklift"),
            (f"{SYN}forklift", RDF_TYPE, f"{INF}PoweredIndustrialTruck"),
            (
                f"{INF}PoweredIndustrialTruck",
                OWL_EQUIVALENT_CLASS,
                f"{INF}CertifiedMachine",
            ),
            (f"{INF}CertifiedMachine", INF_NAME, "vehicle is certified"),
            (f"{INF}CertifiedMachine", INF_CONFIDENCE, "0.99"),
        ]
    )

    result = _reasoner().materialize(
        "vehicle classification",
        FactValue("forklift"),
        index,
    )

    assert [item.fact_name for item in result.derived_facts] == [
        "vehicle is certified"
    ]
    trace = next(item for item in result.trace if item["status"] == "materialized")
    assert trace["derivationRule"] == "owl_equivalent_class_closure"


def test_can_derive_returns_current_fact_derivability():
    index = OntologyIndex(
        [
            (f"{SYN}forklift", INF_NAME, "forklift"),
            (f"{SYN}forklift", RDF_TYPE, f"{INF}IndustrialVehicle"),
            (f"{INF}IndustrialVehicle", RDFS_SUBCLASS_OF, f"{INF}TypeApprovedEquipment"),
            (f"{INF}TypeApprovedEquipment", INF_NAME, "vehicle is type approved"),
            (f"{INF}TypeApprovedEquipment", INF_CONFIDENCE, "0.95"),
        ]
    )
    store = LayeredFactStore()
    store.set_fact("vehicle classification", FactValue("forklift"), FactSource.ASSERTED)

    can_derive, fact_value, confidence = _reasoner().can_derive(
        "vehicle is type approved",
        store,
        index,
    )

    assert can_derive is True
    assert fact_value.get_value() is True
    assert confidence == 0.95
