"""Focused branch coverage for the INFERRA-to-RDF compiler."""

from src.adapters.outbound.ontology.inferra_to_rdf_compiler import (
    INF_NS,
    RDF_TYPE,
    InferraToRdfCompiler,
    _append_metadata_triples,
    _extract_quantifier,
)


def test_orphaned_and_modifier_only_children_are_ignored() -> None:
    orphaned = InferraToRdfCompiler.compile(
        "    AND orphaned child",
        "orphaned",
    )
    modifier_only = InferraToRdfCompiler.compile(
        "decision\n    AND",
        "modifier_only",
    )

    assert not any(predicate.endswith("dependsOn") for _, predicate, _ in orphaned)
    assert not any(predicate.endswith("DependsOn") for _, predicate, _ in modifier_only)


def test_undeclared_required_and_comparison_variables_are_materialized() -> None:
    triples = InferraToRdfCompiler.compile(
        "decision\n"
        "    NEEDS external signal\n"
        "    AND claim amount > 5\n",
        "variable_fallbacks",
    )
    root_uri = f"{INF_NS}rule/variable_fallbacks/node/decision"
    required_uri = f"{INF_NS}rule/variable_fallbacks/declaration/external_signal"
    comparison_variable_uri = (
        f"{INF_NS}rule/variable_fallbacks/declaration/claim_amount"
    )

    assert (root_uri, f"{INF_NS}requiresVariable", required_uri) in triples
    assert (required_uri, RDF_TYPE, f"{INF_NS}Variable") in triples
    assert (required_uri, f"{INF_NS}name", "external signal") in triples
    assert (comparison_variable_uri, RDF_TYPE, f"{INF_NS}Variable") in triples
    assert (comparison_variable_uri, f"{INF_NS}name", "claim amount") in triples


def test_unknown_metadata_keys_are_not_emitted() -> None:
    triples = []

    _append_metadata_triples(
        triples,
        "urn:node:decision",
        {"UNKNOWN": ["ignored"], "REFERENCE": ["MRCA s 199"]},
    )

    assert triples == [
        ("urn:node:decision", f"{INF_NS}statutoryReference", "MRCA s 199")
    ]


def test_wants_dependency_maps_to_or_and_numeric_quantifier_is_preserved() -> None:
    triples = InferraToRdfCompiler.compile(
        "decision\n    WANTS alternative path",
        "wants_dependency",
    )
    root_uri = f"{INF_NS}rule/wants_dependency/node/decision"
    child_uri = f"{INF_NS}rule/wants_dependency/node/alternative_path"

    assert (root_uri, f"{INF_NS}orDependsOn", child_uri) in triples
    assert _extract_quantifier("2 item IN items") == "2"
