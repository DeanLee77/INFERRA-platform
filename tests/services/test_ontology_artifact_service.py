import json
from pathlib import Path

import pytest

from src.adapters.outbound.ontology.fuseki_adapter import INF_NS
from src.adapters.outbound.ontology.inferra_to_rdf_compiler import RDF_TYPE
from src.services.ontology_artifact_service import (
    ADVISORY_GUARDRAIL,
    build_case_run_ontology_artifact,
    build_rule_set_ontology_artifact,
    full_artifact_name,
    rule_artifact_name,
)

rdflib = pytest.importorskip("rdflib")


DRCA_RULE = "drca_part_ii_sections_14_to_33"


def test_rule_set_artifact_uses_expected_drca_name_and_parseable_turtle():
    triples = [
        (f"{INF_NS}rule/{DRCA_RULE}", RDF_TYPE, f"{INF_NS}RuleSet"),
        (f"{INF_NS}rule/{DRCA_RULE}", f"{INF_NS}name", DRCA_RULE),
    ]

    artifact = build_rule_set_ontology_artifact(
        rule_name=DRCA_RULE,
        triples=triples,
        source_hash="rule-source-hash",
        graph_uri=f"{INF_NS}projection/rule/{DRCA_RULE}",
        metadata={"sync_status": "current", "integrity_status": "pass"},
    )

    assert rule_artifact_name(DRCA_RULE) == "drca_part_ii_ontology.ttl"
    assert artifact.artifact_name == "drca_part_ii_ontology.ttl"
    assert artifact.projection_graph_uri == f"{INF_NS}projection/rule/{DRCA_RULE}"
    assert ADVISORY_GUARDRAIL in artifact.turtle

    graph = rdflib.Graph()
    graph.parse(data=artifact.turtle, format="turtle")
    assert len(graph) == artifact.triple_count


def test_case_run_full_artifact_includes_robert_case_facts_and_outcome_ref():
    robert_fixture = Path("tests/fixtures/cases/Robert.json")
    robert_case = json.loads(robert_fixture.read_text(encoding="utf-8"))
    rule_ontology = {
        "rule_name": DRCA_RULE,
        "source_hash": "rule-source-hash",
        "graph_uri": f"{INF_NS}projection/rule/{DRCA_RULE}",
        "triples": [
            {
                "subject": f"{INF_NS}rule/{DRCA_RULE}",
                "predicate": RDF_TYPE,
                "object": f"{INF_NS}RuleSet",
            },
            {
                "subject": f"{INF_NS}rule/{DRCA_RULE}",
                "predicate": f"{INF_NS}name",
                "object": DRCA_RULE,
            },
        ],
    }

    artifact = build_case_run_ontology_artifact(
        rule_ontology=rule_ontology,
        session_id="Robert-session",
        case_name=robert_case["case_name"],
        target_node_name=robert_case["target_node_name"],
        facts=[
            {
                "name": "impairment points",
                "value": robert_case["facts"]["impairment points"],
                "sources": ["ASSERTED"],
            },
            {
                "name": "incapacity status",
                "value": robert_case["facts"]["incapacity status"],
                "sources": ["ASSERTED"],
            },
            {
                "name": robert_case["target_node_name"],
                "value": robert_case["facts"][robert_case["target_node_name"]],
                "sources": ["INFERRED"],
            },
        ],
        status="GOAL_REACHED",
    )

    assert full_artifact_name(DRCA_RULE) == "drca_part_ii_full_ontology.ttl"
    assert artifact.artifact_name == "drca_part_ii_full_ontology.ttl"
    assert artifact.case_name == "Robert.json"
    assert artifact.deterministic_outcome_ref is not None
    assert "DRCA part II sections 14 to 33 convergence met" in artifact.turtle
    assert ADVISORY_GUARDRAIL in artifact.turtle

    graph = rdflib.Graph()
    graph.parse(data=artifact.turtle, format="turtle")
    assert len(graph) == artifact.triple_count


def test_case_run_full_artifact_includes_semantic_provenance_and_authority():
    rule_ontology = {
        "rule_name": DRCA_RULE,
        "source_hash": "rule-source-hash",
        "graph_uri": f"{INF_NS}projection/rule/{DRCA_RULE}",
        "triples": [
            {
                "subject": f"{INF_NS}rule/{DRCA_RULE}",
                "predicate": RDF_TYPE,
                "object": f"{INF_NS}RuleSet",
            },
        ],
    }

    artifact = build_case_run_ontology_artifact(
        rule_ontology=rule_ontology,
        session_id="semantic-session",
        target_node_name="eligible",
        facts=[
            {"name": "service type", "value": "warlike service", "sources": ["ASSERTED"]},
            {"name": "DVA operational service type", "value": True, "sources": ["INFERRED"]},
        ],
        ontology_profile="full_semantic_pilot",
        ontology_profile_source="request",
        ontology_flags={
            "ontology_advisory_enabled": True,
            "ontology_auto_answer": True,
            "ontology_reasoning": True,
            "ontology_question_strategy": True,
        },
        ontology_derived_facts=["DVA operational service type"],
        ontology_materialization_trace=[
            {
                "status": "materialized",
                "factName": "DVA operational service type",
                "sourceFactName": "service type",
                "confidence": 0.91,
                "sourceGraphUri": f"{INF_NS}projection/rule/{DRCA_RULE}",
                "ontologySnapshotHash": "rule-source-hash",
                "materializedInference": True,
            }
        ],
        semantic_question_strategy_trace=[
            {
                "questionName": "service type",
                "action": "selected",
                "reason": "highest_semantic_question_score",
            }
        ],
    )

    assert "SemanticDerivedFact" in artifact.turtle
    assert "canSatisfyAuthoritativeRules" in artifact.turtle
    assert "OntologyMaterializationTrace" in artifact.turtle
    assert "SemanticQuestionStrategyTrace" in artifact.turtle
    assert "highest_semantic_question_score" in artifact.turtle

    graph = rdflib.Graph()
    graph.parse(data=artifact.turtle, format="turtle")
    assert len(graph) == artifact.triple_count
