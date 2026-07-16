from __future__ import annotations

import builtins
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from src.adapters.inbound.http.routes import ontology
from src.adapters.inbound.http.schemas.ontology import (
    OntologyChatBindingValue,
    OntologyChatGraphOverlayTargets,
    OntologyChatGuardrailReceipt,
    OntologyChatQueryCandidate,
    OntologyChatQueryRequest,
    OntologyDecisionPathEdge,
    OntologyPathResolveRequest,
)
from src.adapters.outbound.ontology.fuseki_adapter import FusekiConnectionError


FULL_GRAPH = "http://inferra.ai/schema#case-run/demo/full-semantic/case-1"
PROJECTION_GRAPH = "http://inferra.ai/schema#projection/rule/demo"
RUN_URI = "http://inferra.ai/schema#session/case-1"
FACT_URI = f"{RUN_URI}/fact/input"
TARGET_URI = f"{RUN_URI}/fact/outcome"
TRACE_URI = f"{RUN_URI}/trace/1"
PROJECTION_INPUT = "http://inferra.ai/schema#rule/demo/node/input"
PROJECTION_TARGET = "http://inferra.ai/schema#rule/demo/node/outcome"


def _receipt() -> OntologyChatGuardrailReceipt:
    return ontology._guardrail_receipt(
        selected_graphs=[PROJECTION_GRAPH],
        available_graph_count=1,
        query_length=20,
        row_limit=10,
        timeout_seconds=2,
        max_retries=0,
    )


def _query_request(
    sparql: str | None = None,
    *,
    candidate: bool = True,
) -> OntologyChatQueryRequest:
    query_candidate = None
    if candidate:
        query_candidate = OntologyChatQueryCandidate(
            status="query",
            sparql=sparql
            or (
                "SELECT ?s WHERE { "
                f"GRAPH <{PROJECTION_GRAPH}> {{ ?s ?p ?o }} "
                "} LIMIT 10"
            ),
        )
    return OntologyChatQueryRequest(
        question="Which items are connected?",
        selected_graph_uris=[PROJECTION_GRAPH],
        candidate=query_candidate,
        row_limit=10,
        timeout_seconds=2,
    )


def _path_request(**overrides) -> OntologyPathResolveRequest:
    values = {"selected_graph_uris": [FULL_GRAPH]}
    values.update(overrides)
    return OntologyPathResolveRequest(**values)


def _empty_context() -> dict:
    return ontology._load_decision_path_context([], [])


def _case_run(*, target_ref: str | None = TARGET_URI) -> dict:
    return {
        "uri": RUN_URI,
        "graph_uri": FULL_GRAPH,
        "case_name": "case-1",
        "rule_name": "demo",
        "target_node_name": "outcome",
        "deterministic_outcome_ref": target_ref,
        "deterministic_outcome_name": "outcome",
        "deterministic_outcome_value": "true",
    }


def _path_edge(
    relationship_type: str = "semantic_trace",
) -> OntologyDecisionPathEdge:
    return OntologyDecisionPathEdge(
        source_uri=FACT_URI,
        predicate_uri=f"{ontology.INF_NS}dependsOn",
        target_uri=TARGET_URI,
        label="depends On",
        graph_uri=FULL_GRAPH,
        relationship_type=relationship_type,
        direction="evidence_to_conclusion",
    )


@pytest.mark.asyncio
async def test_chat_query_maps_fuseki_connection_failure(monkeypatch):
    monkeypatch.setattr(
        ontology.FusekiAdapter,
        "list_named_graphs",
        lambda: [(PROJECTION_GRAPH, 3)],
    )
    monkeypatch.setattr(
        ontology.FusekiAdapter,
        "execute_guarded_select",
        MagicMock(side_effect=FusekiConnectionError("offline")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await ontology.query_ontology_chat(_query_request())

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail["error"] == "fuseki_query_failed"
    assert exc_info.value.detail["guardrail_receipt"]["read_only"] is True


@pytest.mark.asyncio
async def test_path_route_validates_active_graph_and_maps_query_failure(monkeypatch):
    monkeypatch.setattr(
        ontology.FusekiAdapter,
        "list_named_graphs",
        lambda: [(FULL_GRAPH, 3)],
    )
    with pytest.raises(HTTPException, match="absolute"):
        await ontology.resolve_ontology_decision_path(
            _path_request(active_graph_uri="relative")
        )

    monkeypatch.setattr(
        ontology,
        "_load_decision_path_context",
        MagicMock(side_effect=FusekiConnectionError("offline")),
    )
    with pytest.raises(HTTPException) as exc_info:
        await ontology.resolve_ontology_decision_path(
            _path_request(active_graph_uri=FULL_GRAPH)
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == {
        "error": "fuseki_path_query_failed",
        "message": "offline",
    }


def test_authoritative_graph_selection_covers_fallbacks():
    warnings: list[str] = []
    assert ontology._authoritative_full_semantic_graphs(
        [FULL_GRAPH, PROJECTION_GRAPH], warnings
    ) == [FULL_GRAPH]
    assert warnings == []

    plain_graph = "urn:inferra:unclassified"
    assert ontology._authoritative_full_semantic_graphs(
        [plain_graph, PROJECTION_GRAPH], warnings
    ) == [plain_graph]
    assert "non-projection" in warnings[-1]

    assert ontology._authoritative_full_semantic_graphs(
        [PROJECTION_GRAPH], warnings
    ) == []
    assert "Select a Full Semantic graph" in warnings[-1]
    assert ontology._is_full_semantic_graph(FULL_GRAPH)
    assert ontology._is_projection_graph(PROJECTION_GRAPH)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ([], None),
        ([{}], None),
        ([{"version": {"value": FULL_GRAPH}}], FULL_GRAPH),
    ],
)
def test_latest_full_semantic_pointer_resolution(monkeypatch, result, expected):
    latest = "http://inferra.ai/graphs/full-semantic/latest"
    monkeypatch.setattr(
        ontology.FusekiAdapter,
        "execute_guarded_select",
        MagicMock(return_value=result),
    )

    assert ontology._resolve_latest_full_semantic_pointer(latest) == (expected or latest)
    assert ontology._resolve_latest_full_semantic_pointer(FULL_GRAPH) == FULL_GRAPH


def test_latest_full_semantic_pointer_tolerates_lookup_failure(monkeypatch):
    latest = "http://inferra.ai/graphs/full-semantic/latest"
    monkeypatch.setattr(
        ontology.FusekiAdapter,
        "execute_guarded_select",
        MagicMock(side_effect=RuntimeError("bad pointer")),
    )

    assert ontology._resolve_latest_full_semantic_pointer(latest) == latest


def test_trace_and_projection_context_loaders_cover_sparse_and_capped_rows(monkeypatch):
    context = _empty_context()
    monkeypatch.setattr(
        ontology,
        "_execute_path_select",
        MagicMock(
            side_effect=[
                [
                    {"trace": {"value": "urn:trace:ignored"}},
                    {
                        "graph": {"value": FULL_GRAPH},
                        "trace": {"value": TRACE_URI},
                        "traceType": {"value": f"{ontology.INF_NS}OntologyAutoAnswerTrace"},
                        "traceKind": {"value": "auto-answer"},
                        "questionName": {"value": "input"},
                        "nodeName": {"value": "input check"},
                        "factName": {"value": "input"},
                        "sourceFactName": {"value": "source input"},
                        "status": {"value": "used"},
                        "action": {"value": "answer"},
                        "reason": {"value": "matched"},
                        "generatedBy": {"value": RUN_URI},
                    },
                ],
                [
                    {"graph": {"value": PROJECTION_GRAPH}},
                    {
                        "graph": {"value": PROJECTION_GRAPH},
                        "node": {"value": PROJECTION_INPUT},
                        "name": {"value": "input"},
                        "type": {"value": f"{ontology.INF_NS}RuleNode"},
                    },
                ],
                [
                    {"source": {"value": "urn:ignored"}},
                    {
                        "graph": {"value": PROJECTION_GRAPH},
                        "source": {"value": PROJECTION_INPUT},
                        "predicate": {"value": f"{ontology.INF_NS}dependsOn"},
                        "target": {"value": PROJECTION_TARGET},
                    },
                ],
            ]
        ),
    )
    monkeypatch.setattr(ontology, "PATH_RESULT_LIMIT", 2)

    ontology._load_trace_context([FULL_GRAPH], context)
    ontology._load_projection_context([PROJECTION_GRAPH], context)

    assert context["traces_by_uri"][TRACE_URI]["reason"] == "matched"
    assert context["projection_nodes_by_uri"][PROJECTION_INPUT]["types"] == [
        f"{ontology.INF_NS}RuleNode"
    ]
    assert len(context["projection_edges"]) == 1
    assert context["projection_node_limit_hit"] is True
    assert context["projection_edge_limit_hit"] is True


def test_selected_trace_builds_authoritative_path():
    context = _empty_context()
    run = _case_run()
    trace = {
        "uri": TRACE_URI,
        "graph_uri": FULL_GRAPH,
        "trace_type": None,
        "trace_kind": None,
        "question_name": "input",
        "node_name": "input check",
        "fact_name": None,
        "source_fact_name": None,
        "status": None,
        "action": None,
        "reason": None,
        "generated_by": RUN_URI,
    }
    context["case_runs"] = [run]
    context["case_runs_by_uri"][RUN_URI] = run
    context["traces_by_uri"][TRACE_URI] = trace

    response = ontology._resolve_decision_path(
        request=_path_request(selected_uri=TRACE_URI),
        authoritative_graphs=[FULL_GRAPH],
        structural_graphs=[],
        context=context,
        warnings=[],
    )

    assert response.status == "ok"
    assert response.selected_label == "input check"
    assert {edge.relationship_type for edge in response.edges} == {
        "semantic_trace",
        "authoritative_outcome",
    }


def test_selected_projection_case_run_and_unknown_selection_branches():
    projection_context = _empty_context()
    projection = {
        "uri": PROJECTION_INPUT,
        "graph_uri": PROJECTION_GRAPH,
        "name": "input",
        "types": [],
    }
    projection_context["projection_nodes_by_uri"][PROJECTION_INPUT] = projection
    projection_response = ontology._resolve_decision_path(
        request=_path_request(selected_uri=PROJECTION_INPUT),
        authoritative_graphs=[],
        structural_graphs=[PROJECTION_GRAPH],
        context=projection_context,
        warnings=[],
    )
    assert projection_response.nodes[0].match_kind == "exact_uri"
    assert any("CaseRun target" in warning for warning in projection_response.warnings)

    run_context = _empty_context()
    run = _case_run()
    run_context["case_runs"] = [run]
    run_context["case_runs_by_uri"][RUN_URI] = run
    run_response = ontology._resolve_decision_path(
        request=_path_request(selected_uri=RUN_URI),
        authoritative_graphs=[FULL_GRAPH],
        structural_graphs=[],
        context=run_context,
        warnings=[],
    )
    assert run_response.status == "ok"
    assert any(edge.relationship_type == "authoritative_outcome" for edge in run_response.edges)

    unknown_uri = "urn:inferra:unknown"
    unknown_response = ontology._resolve_decision_path(
        request=_path_request(selected_uri=unknown_uri, selected_label="Unknown item"),
        authoritative_graphs=[],
        structural_graphs=[],
        context=_empty_context(),
        warnings=[],
    )
    assert unknown_response.selected_uri == unknown_uri
    assert any("was not found" in warning for warning in unknown_response.warnings)


@pytest.mark.parametrize(
    ("path_request", "warning"),
    [
        (_path_request(selected_label="missing"), "No exact normalized"),
        (_path_request(), "Select a result row"),
    ],
)
def test_unmatched_and_empty_path_selections(path_request, warning):
    response = ontology._resolve_decision_path(
        request=path_request,
        authoritative_graphs=[],
        structural_graphs=[],
        context=_empty_context(),
        warnings=[],
    )

    assert response.status == "no_path"
    assert warning in response.warnings[0]


def test_target_name_without_resolvable_uri_warns(monkeypatch):
    context = _empty_context()
    run = _case_run(target_ref=None)
    context["case_runs"] = [run]
    context["case_runs_by_uri"][RUN_URI] = run
    monkeypatch.setattr(ontology, "_target_uri", lambda *_args: None)

    response = ontology._resolve_decision_path(
        request=_path_request(selected_uri=RUN_URI),
        authoritative_graphs=[FULL_GRAPH],
        structural_graphs=[],
        context=context,
        warnings=[],
    )

    assert any("no matching deterministic outcome URI" in warning for warning in response.warnings)


def test_identified_source_and_target_without_edges_reports_no_path():
    context = _empty_context()
    run = _case_run()
    context["case_runs"] = [run]
    context["case_runs_by_uri"][RUN_URI] = run

    response = ontology._resolve_decision_path(
        request=_path_request(selected_uri="urn:inferra:unmapped-selection"),
        authoritative_graphs=[FULL_GRAPH],
        structural_graphs=[],
        context=context,
        warnings=[],
    )

    assert response.status == "no_path"
    assert any("no explicit path edge" in warning for warning in response.warnings)


def test_structural_path_warnings_cover_no_path_and_missing_matches():
    context = _empty_context()
    run = _case_run()
    fact = {
        "uri": FACT_URI,
        "graph_uri": FULL_GRAPH,
        "name": "input",
        "value": "yes",
        "sources": [],
        "session_uri": RUN_URI,
    }
    target_projection = {
        "uri": PROJECTION_TARGET,
        "graph_uri": PROJECTION_GRAPH,
        "name": "outcome",
        "types": [],
    }
    input_projection = {
        "uri": PROJECTION_INPUT,
        "graph_uri": PROJECTION_GRAPH,
        "name": "input",
        "types": [],
    }
    context["case_runs"] = [run]
    context["case_runs_by_uri"][RUN_URI] = run
    context["facts_by_uri"][FACT_URI] = fact
    context["facts_by_name"]["input"] = [fact]
    context["projection_nodes_by_uri"].update(
        {PROJECTION_INPUT: input_projection, PROJECTION_TARGET: target_projection}
    )
    context["projection_nodes_by_name"].update(
        {"input": [input_projection], "outcome": [target_projection]}
    )
    context["projection_node_limit_hit"] = True

    response = ontology._resolve_decision_path(
        request=_path_request(selected_uri=FACT_URI, max_depth=1),
        authoritative_graphs=[FULL_GRAPH],
        structural_graphs=[PROJECTION_GRAPH],
        context=context,
        warnings=[],
    )
    assert any("row cap" in warning for warning in response.warnings)
    assert any("no explicit path edge" in warning for warning in response.warnings) is False

    no_start = _empty_context()
    no_start["case_runs"] = [run]
    no_start["case_runs_by_uri"][RUN_URI] = run
    response = ontology._resolve_decision_path(
        request=_path_request(selected_uri=RUN_URI),
        authoritative_graphs=[FULL_GRAPH],
        structural_graphs=[PROJECTION_GRAPH],
        context=no_start,
        warnings=[],
    )
    assert any("selected item" in warning for warning in response.warnings)


def test_projection_and_path_helpers_cover_boundaries():
    context = _empty_context()
    projection = {
        "uri": PROJECTION_INPUT,
        "graph_uri": PROJECTION_GRAPH,
        "name": "input",
        "types": [],
    }
    context["projection_nodes_by_name"]["input"] = [projection]
    trace = {
        "uri": TRACE_URI,
        "question_name": "input",
        "node_name": None,
        "fact_name": None,
        "source_fact_name": None,
    }
    assert ontology._projection_node_for_selected_item(None, trace, None, context) == projection
    assert ontology._projection_node_for_labels([None, "missing"], context) is None
    assert ontology._structural_source_label([PROJECTION_GRAPH]) == "Rule Projection"
    assert ontology._structural_source_label([FULL_GRAPH]) == "Full Semantic structural"
    warning = ontology._structural_no_path_warning(
        structural_graphs=[FULL_GRAPH],
        existing_edges=False,
        max_depth=3,
        context={},
        projection_start={"name": "input"},
        projection_target={"name": "outcome"},
    )
    assert "usually means" in warning

    edge = {
        "graph_uri": PROJECTION_GRAPH,
        "source_uri": PROJECTION_INPUT,
        "predicate_uri": f"{ontology.INF_NS}dependsOn",
        "target_uri": PROJECTION_TARGET,
    }
    assert ontology._projection_bfs(PROJECTION_INPUT, PROJECTION_INPUT, [], max_depth=1) == []
    assert ontology._projection_bfs(PROJECTION_INPUT, PROJECTION_TARGET, [edge], max_depth=0) is None
    cyclic = [edge, {**edge, "source_uri": PROJECTION_TARGET, "target_uri": PROJECTION_INPUT}]
    assert ontology._projection_bfs(PROJECTION_INPUT, "urn:missing", cyclic, max_depth=3) is None


def test_node_edge_ordering_and_summary_helpers():
    nodes = {}
    ontology._add_path_node(nodes, "", "empty", FULL_GRAPH, role="fact", match_kind="related")
    ontology._add_path_node(
        nodes,
        FACT_URI,
        "",
        FULL_GRAPH,
        role="selected",
        match_kind="exact_uri",
    )
    ontology._add_path_node(
        nodes,
        FACT_URI,
        "lower priority",
        FULL_GRAPH,
        role="fact",
        match_kind="related",
    )
    assert nodes[FACT_URI].label == "input"
    assert nodes[FACT_URI].role == "selected"
    assert ontology._role_priority("unexpected") == 0

    edges = {}
    ontology._add_path_edge(
        edges,
        "",
        "urn:predicate",
        TARGET_URI,
        FULL_GRAPH,
        relationship_type="unknown",
        direction="stored",
    )
    assert edges == {}
    forward = [_path_edge("semantic_trace"), _path_edge("authoritative_case_fact")]
    reverse = ontology._ordered_edges(forward, "conclusion_to_evidence")
    assert [edge.relationship_type for edge in reverse] == [
        "semantic_trace",
        "authoritative_case_fact",
    ]
    assert "depends On" in ontology._relationship_summary(forward)[0]


def test_request_item_and_target_helpers_cover_fallbacks():
    request = _path_request(selected_uri=f"  {FACT_URI}  ", selected_label="  input  ")
    assert ontology._selected_uri_from_request(request) == FACT_URI
    assert ontology._selected_label_from_request(request) == "input"

    row_request = _path_request(
        selected_row={
            "questionName": {"type": "literal", "value": "question"},
            "fallback": {"type": "uri", "value": TRACE_URI},
        }
    )
    assert ontology._selected_uri_from_request(row_request) == TRACE_URI
    assert ontology._selected_label_from_request(row_request) == "question"
    assert ontology._selected_uri_from_request(_path_request()) is None
    assert ontology._selected_label_from_request(_path_request()) is None

    item = {"uri": FACT_URI}
    assert ontology._match_item(FACT_URI, None, {FACT_URI: item}, {}) == item
    assert ontology._match_item(None, "missing", {}, {}) is None
    assert ontology._preferred_case_run([], FULL_GRAPH) is None
    cases = [
        {"uri": "urn:z", "graph_uri": "urn:z"},
        {"uri": "urn:a", "graph_uri": FULL_GRAPH},
    ]
    assert ontology._preferred_case_run(cases, FULL_GRAPH)["uri"] == "urn:a"
    assert ontology._preferred_case_run(cases, "urn:other")["uri"] == "urn:a"
    assert ontology._case_run_target_name(None) is None

    run = _case_run()
    context = _empty_context()
    assert ontology._target_uri(run, "outcome", context) == TARGET_URI
    run["deterministic_outcome_ref"] = "not-a-uri"
    same_graph = {"uri": TARGET_URI, "graph_uri": FULL_GRAPH}
    other_graph = {"uri": "urn:other", "graph_uri": "urn:other"}
    context["facts_by_name"]["outcome"] = [other_graph, same_graph]
    assert ontology._target_uri(run, "outcome", context) == TARGET_URI
    context["facts_by_name"]["outcome"] = [other_graph]
    assert ontology._target_uri(run, "outcome", context) == "urn:other"
    context["facts_by_name"].clear()
    assert ontology._target_uri(run, "missing", context) == RUN_URI
    assert ontology._target_uri(None, "outcome", context) is None
    assert ontology._target_graph_uri("urn:missing", run, context) == FULL_GRAPH
    assert ontology._target_graph_uri("urn:missing", None, context) == ""


def test_trace_index_binding_and_text_helpers_cover_sparse_values():
    duplicate = {"uri": TRACE_URI}
    context = _empty_context()
    context["traces_by_name"]["input"] = [duplicate, duplicate]
    traces = ontology._traces_for_labels([None, "input", "input"], context)
    assert traces == [duplicate]
    assert ontology._trace_display_label({"uri": TRACE_URI}) == "1"

    index = {}
    ontology._index_by_normalized_name(index, None, duplicate)
    ontology._index_by_normalized_name(index, " Input  Name ", duplicate)
    ontology._index_by_normalized_name(index, "input name", duplicate)
    assert index == {"input name": [duplicate]}

    assert ontology._binding_value({"value": 7}, "value") == "7"
    assert ontology._binding_value({}, "missing") is None
    assert ontology._normalize_label(None) == ""
    assert ontology._predicate_label("urn:test:camelCase_name") == "camel Case name"
    assert ontology._unique_stable(["", "a", "a", "b"]) == ["a", "b"]


def test_graph_inventory_and_selection_errors(monkeypatch):
    monkeypatch.setattr(
        ontology.FusekiAdapter,
        "list_named_graphs",
        MagicMock(side_effect=FusekiConnectionError("offline")),
    )
    with pytest.raises(HTTPException) as exc_info:
        ontology._list_available_graphs()
    assert exc_info.value.status_code == 503

    with pytest.raises(HTTPException) as exc_info:
        ontology._validate_selected_graphs([PROJECTION_GRAPH], {})
    assert exc_info.value.detail["error"] == "selected_graph_not_available"


def test_chat_sparql_resolution_covers_template_and_missing_candidate():
    request = _query_request(candidate=False)
    sparql, source, version, rationale = ontology._resolve_chat_sparql(
        request, [PROJECTION_GRAPH]
    )
    assert source == "deterministic_template"
    assert version == "deterministic-template-v1"
    assert rationale
    assert f"GRAPH ?graph" in sparql

    missing = OntologyChatQueryCandidate(status="query", sparql=None)
    with pytest.raises(HTTPException) as exc_info:
        ontology._resolve_chat_sparql(request, [PROJECTION_GRAPH], candidate=missing)
    assert exc_info.value.detail["error"] == "candidate_missing_sparql"

    supplied = OntologyChatQueryCandidate(status="query", sparql=" SELECT * WHERE {} LIMIT 1 ")
    resolved = ontology._resolve_chat_sparql(
        request, [PROJECTION_GRAPH], candidate=supplied
    )
    assert resolved[:3] == (
        "SELECT * WHERE {} LIMIT 1",
        "structured_candidate",
        "ontology-chat-query-v1",
    )


@pytest.mark.parametrize(
    ("sparql", "error"),
    [
        ("x" * (ontology.MAX_CHAT_QUERY_LENGTH + 1), "query_too_long"),
        ("ASK WHERE {}", "query_must_be_select"),
        (
            f"SELECT ?s FROM <{PROJECTION_GRAPH}> WHERE {{ ?s ?p ?o }} LIMIT 1",
            "unsafe_sparql_operation",
        ),
    ],
)
def test_guarded_sparql_rejects_length_operation_and_from(sparql, error):
    with pytest.raises(HTTPException) as exc_info:
        ontology._validate_guarded_sparql(
            sparql,
            selected_graphs=[PROJECTION_GRAPH],
            row_limit=10,
            receipt=_receipt(),
        )
    assert exc_info.value.detail["error"] == error


def test_query_operation_handles_directives_comments_and_empty_text():
    query = (
        "# leading comment\n"
        "PREFIX inf: <http://inferra.ai/schema#> "
        "BASE <http://inferra.ai/> SELECT * WHERE {}"
    )
    assert ontology._query_operation(query) == "SELECT"
    assert ontology._query_operation("# comment only") is None
    assert "SERVICE" not in ontology._sparql_tokens(
        'SELECT * WHERE { BIND("SERVICE" AS ?label) GRAPH <urn:SERVICE> {} }'
    )


def _without_import(monkeypatch, blocked_name: str) -> None:
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == blocked_name:
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)


def test_sparql_parse_fallback_validates_braces_and_where(monkeypatch):
    _without_import(monkeypatch, "rdflib.plugins.sparql.parser")
    ontology._validate_sparql_parse("SELECT ?s WHERE { ?s ?p ?o }", _receipt())

    with pytest.raises(HTTPException) as exc_info:
        ontology._validate_sparql_parse("SELECT ?s WHERE {", _receipt())
    assert exc_info.value.detail["error"] == "invalid_sparql"

    with pytest.raises(HTTPException) as exc_info:
        ontology._validate_sparql_parse("SELECT ?s { ?s ?p ?o }", _receipt())
    assert "WHERE" in exc_info.value.detail["message"]


def test_sparql_parser_and_scope_parser_failures(monkeypatch):
    with pytest.raises(HTTPException) as exc_info:
        ontology._validate_sparql_parse("SELECT ?s WHERE {", _receipt())
    assert exc_info.value.detail["error"] == "invalid_sparql"

    _without_import(monkeypatch, "pyparsing")
    with pytest.raises(HTTPException) as exc_info:
        ontology._validate_no_default_graph_patterns("SELECT * WHERE {}", _receipt())
    assert exc_info.value.detail["error"] == "sparql_parser_unavailable"


def test_default_graph_scope_parser_rejection(monkeypatch):
    from rdflib.plugins.sparql import parser

    monkeypatch.setattr(parser, "parseQuery", MagicMock(side_effect=ValueError("bad")))
    with pytest.raises(HTTPException) as exc_info:
        ontology._validate_no_default_graph_patterns("SELECT * WHERE {}", _receipt())
    assert exc_info.value.detail["error"] == "invalid_sparql"


@pytest.mark.parametrize(
    ("sparql", "error"),
    [
        ("SELECT ?s WHERE { GRAPH ?g { ?s ?p ?o } } LIMIT 1", "unbound_graph_scope"),
        ("SELECT ?s WHERE { ?s ?p ?o } LIMIT 1", "unscoped_graph_query"),
    ],
)
def test_graph_scope_requires_bound_explicit_graphs(sparql, error):
    with pytest.raises(HTTPException) as exc_info:
        ontology._validate_graph_scope(
            sparql,
            [PROJECTION_GRAPH],
            _receipt(),
        )
    assert exc_info.value.detail["error"] == error


def test_graph_scope_extraction_handles_bound_and_unbound_variables():
    sparql = (
        f"VALUES ?g {{ <{PROJECTION_GRAPH}> }} "
        "GRAPH ?g { ?s ?p ?o } GRAPH ?unbound { ?a ?b ?c }"
    )
    refs, unbound = ontology._extract_graph_scope_uris(sparql)
    assert refs == {PROJECTION_GRAPH}
    assert unbound == {"?unbound"}


@pytest.mark.parametrize(
    ("sparql", "error"),
    [
        ("SELECT * WHERE {}", "unbounded_query"),
        ("SELECT * WHERE {} LIMIT 11", "over_limit_query"),
    ],
)
def test_limit_guard_rejects_missing_and_excessive_limits(sparql, error):
    with pytest.raises(HTTPException) as exc_info:
        ontology._validate_limit(sparql, 10, _receipt())
    assert exc_info.value.detail["error"] == error


def test_rows_overlay_and_provenance_helpers_cover_fallbacks():
    rows = ontology._rows_from_bindings(
        [
            {
                "subject": {"type": "uri", "value": FACT_URI},
                "raw": 7,
            }
        ]
    )
    assert rows[0]["raw"].value == "7"

    overlays = ontology._overlay_targets(rows, [FULL_GRAPH])
    assert overlays[FULL_GRAPH].nodes[FACT_URI].row_indices == [0]
    outside = ontology._overlay_targets(
        [
            {
                "graph": OntologyChatBindingValue(type="uri", value="urn:outside"),
                "subject": OntologyChatBindingValue(type="uri", value=FACT_URI),
            }
        ],
        [FULL_GRAPH, PROJECTION_GRAPH],
    )
    assert all(not overlay.nodes for overlay in outside.values())

    overlay = OntologyChatGraphOverlayTargets()
    ontology._append_node_overlay(overlay, FACT_URI, 0)
    ontology._append_node_overlay(overlay, FACT_URI, 0)
    ontology._append_edge_overlay(
        overlay, FACT_URI, f"{ontology.INF_NS}dependsOn", TARGET_URI, 0
    )
    ontology._append_edge_overlay(
        overlay, FACT_URI, f"{ontology.INF_NS}dependsOn", TARGET_URI, 0
    )
    assert overlay.nodes[FACT_URI].row_indices == [0]
    assert next(iter(overlay.edges.values())).row_indices == [0]

    assert ontology._chat_provenance("template", executed=False)["execution_backend"] is None
    assert ontology._chat_provenance(
        "candidate", executed=True, candidate_provenance={"model": "test"}
    )["candidate"] == {"model": "test"}


@pytest.mark.parametrize("uri", ["relative", "urn:bad<value"])
def test_graph_uri_validation_rejects_relative_and_unsafe_values(uri):
    with pytest.raises(HTTPException) as exc_info:
        ontology._validate_chat_graph_uri(uri)
    assert exc_info.value.detail["error"] == "invalid_graph_uri"


def test_sparql_scrubbers_preserve_literals_and_iris_while_removing_comments():
    sparql = (
        "SELECT '#not-comment' \"escaped\\\"#literal\" "
        "<http://example.test/#iri> # actual comment\n"
        "WHERE { BIND('value' AS ?v) }"
    )
    stripped = ontology._strip_sparql_comments(sparql)
    assert "actual comment" not in stripped
    assert "#not-comment" in stripped
    assert "#literal" in stripped
    assert "#iri" in stripped

    scrubbed = ontology._strip_sparql_literals_comments_and_iris(
        "SELECT '''long''' \"\"\"other\"\"\" 'short' \"quoted\" <urn:item> WHERE {}"
    )
    assert "long" not in scrubbed
    assert "other" not in scrubbed
    assert "urn:item" not in scrubbed
    assert "SELECT" in scrubbed
