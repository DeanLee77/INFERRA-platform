from unittest.mock import patch

from fastapi.testclient import TestClient

from src.main import app
from src.services.ontology_chat_planner import OntologyChatPlan


GRAPH_A = "http://inferra.ai/schema#projection/rule/a"
GRAPH_B = "http://inferra.ai/schema#projection/rule/b"
FULL_GRAPH = "http://inferra.ai/schema#case-run/rule/a/full-semantic/case1"
NODE_A = "http://inferra.ai/schema#rule/a/node/eligible"
NODE_B = "http://inferra.ai/schema#rule/b/node/approved"
PREDICATE = "http://inferra.ai/schema#dependsOn"


def _select_all_candidate(*graphs: str, limit: int = 100) -> OntologyChatPlan:
    values = " ".join(f"<{graph}>" for graph in graphs)
    return OntologyChatPlan(
        status="query",
        sparql=(
            "SELECT ?graph ?subject ?predicate ?object WHERE { "
            f"VALUES ?graph {{ {values} }} "
            "GRAPH ?graph { ?subject ?predicate ?object . } "
            f"}} LIMIT {limit}"
        ),
        rationale="Test LLM candidate.",
        confidence=0.91,
        provenance={"planner": "test"},
    )


def test_ontology_routes_require_read_scope_when_auth_is_enabled():
    protected_paths = {
        "/api/v1/ontology/fuseki/graphs",
        "/api/v1/ontology/fuseki/graph",
        "/api/v1/ontology/chat/query",
        "/api/v1/ontology/path/resolve",
    }
    routes = {getattr(route, "path", ""): route for route in app.routes}

    for path in protected_paths:
        dependencies = getattr(routes[path], "dependencies", [])
        assert [dep.dependency.__closure__[0].cell_contents for dep in dependencies] == ["read"]


def test_list_fuseki_named_graphs_returns_counts():
    with patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.list_named_graphs",
        return_value=[("http://inferra.ai/schema#version/hash", 3)],
    ):
        with TestClient(app) as client:
            response = client.get("/api/v1/ontology/fuseki/graphs")

    assert response.status_code == 200
    assert response.json() == {
        "graphs": [{"uri": "http://inferra.ai/schema#version/hash", "triple_count": 3}],
        "total_count": 1,
    }


def test_get_fuseki_named_graph_returns_triples_and_graph_shape():
    triples = [
        (
            "http://inferra.ai/schema#rule/example",
            "http://inferra.ai/schema#name",
            "example",
        ),
        (
            "http://inferra.ai/schema#rule/example",
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
            "http://inferra.ai/schema#RuleSet",
        ),
        (
            "http://inferra.ai/schema#rule/example",
            "http://inferra.ai/schema#containsNode",
            "http://inferra.ai/schema#rule/example/node/eligible",
        ),
    ]
    with patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.get_named_graph_triples",
        return_value=triples,
    ) as get_triples:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/ontology/fuseki/graph",
                params={"graph_uri": "http://inferra.ai/schema#version/hash"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["graph_uri"] == "http://inferra.ai/schema#version/hash"
    assert body["triple_count"] == 3
    assert len(body["nodes"]) == 2
    assert len(body["edges"]) == 1
    assert body["nodes"][0]["name"] == "example"
    get_triples.assert_called_once_with(
        "http://inferra.ai/schema#version/hash",
        offset=0,
        limit=1000,
    )


def test_chat_query_runs_llm_candidate_over_multiple_selected_graphs():
    bindings = [
        {
            "graph": {"type": "uri", "value": GRAPH_A},
            "subject": {"type": "uri", "value": NODE_A},
            "predicate": {"type": "uri", "value": PREDICATE},
            "object": {"type": "uri", "value": NODE_B},
        },
        {
            "graph": {"type": "uri", "value": GRAPH_B},
            "subject": {"type": "uri", "value": NODE_B},
            "predicate": {"type": "uri", "value": PREDICATE},
            "object": {"type": "literal", "value": "approved"},
        },
    ]
    with patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.list_named_graphs",
        return_value=[(GRAPH_A, 10), (GRAPH_B, 8)],
    ), patch(
        "src.adapters.inbound.http.routes.ontology.plan_ontology_chat_query",
        return_value=_select_all_candidate(GRAPH_A, GRAPH_B, limit=2),
    ), patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.execute_guarded_select",
        return_value=bindings,
    ) as execute:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ontology/chat/query",
                json={
                    "question": "What connects the selected rule graphs?",
                    "selected_graph_uris": [GRAPH_A, GRAPH_B],
                    "row_limit": 2,
                    "timeout_seconds": 4,
                    "max_retries": 1,
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["advisory_only"] is True
    assert body["query_details"]["source"] == "structured_candidate"
    assert body["query_details"]["rationale"] == "Test LLM candidate."
    assert GRAPH_A in body["query_details"]["sparql"]
    assert GRAPH_B in body["query_details"]["sparql"]
    assert body["provenance"]["candidate"]["planner"] == "test"
    assert len(body["rows"]) == 2
    assert body["guardrail_receipt"]["read_only"] is True
    assert body["guardrail_receipt"]["graph_scope_validated"] is True
    assert body["guardrail_receipt"]["deterministic_rule_outcomes_mutated"] is False
    assert body["overlay_targets"][GRAPH_A]["nodes"][NODE_A]["row_indices"] == [0]
    assert len(body["overlay_targets"][GRAPH_A]["edges"]) == 1
    execute.assert_called_once()
    sparql = execute.call_args.args[0]
    assert "VALUES ?graph" in sparql
    assert "LIMIT 2" in sparql
    assert execute.call_args.kwargs == {"timeout_seconds": 4, "max_retries": 1}


def test_chat_query_rejects_unsafe_service_operation():
    sparql = (
        "SELECT ?s WHERE { "
        f"GRAPH <{GRAPH_A}> {{ "
        "SERVICE <https://example.invalid/sparql> { ?s ?p ?o } "
        "} } LIMIT 10"
    )
    with patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.list_named_graphs",
        return_value=[(GRAPH_A, 10)],
    ), patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.execute_guarded_select"
    ) as execute:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ontology/chat/query",
                json={
                    "question": "Can the model call a remote graph?",
                    "selected_graph_uris": [GRAPH_A],
                    "candidate": {
                        "contract_version": "ontology-chat-query-v1",
                        "status": "query",
                        "sparql": sparql,
                    },
                },
            )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "unsafe_sparql_operation"
    assert "SERVICE" in detail["guardrail_receipt"]["blocked_operations"]
    execute.assert_not_called()


def test_chat_query_rejects_out_of_scope_graph_references():
    sparql = (
        "SELECT ?s WHERE { "
        f"GRAPH <{GRAPH_B}> {{ ?s ?p ?o }} "
        "} LIMIT 10"
    )
    with patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.list_named_graphs",
        return_value=[(GRAPH_A, 10), (GRAPH_B, 8)],
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ontology/chat/query",
                json={
                    "question": "Can the query escape selection?",
                    "selected_graph_uris": [GRAPH_A],
                    "candidate": {
                        "contract_version": "ontology-chat-query-v1",
                        "status": "query",
                        "sparql": sparql,
                    },
                },
            )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["error"] == "out_of_scope_graph"
    assert GRAPH_B in detail["guardrail_receipt"]["blocked_operations"]


def test_chat_query_rejects_default_graph_patterns_alongside_scoped_graphs():
    sparql = (
        "SELECT ?s WHERE { "
        f"GRAPH <{GRAPH_A}> {{ ?anchor ?p ?o }} "
        "?s ?p2 ?o2 "
        "} LIMIT 10"
    )
    with patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.list_named_graphs",
        return_value=[(GRAPH_A, 10)],
    ), patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.execute_guarded_select"
    ) as execute:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ontology/chat/query",
                json={
                    "question": "Can a candidate also query the default graph?",
                    "selected_graph_uris": [GRAPH_A],
                    "candidate": {
                        "contract_version": "ontology-chat-query-v1",
                        "status": "query",
                        "sparql": sparql,
                    },
                },
            )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "unscoped_default_graph_access"
    execute.assert_not_called()


def test_chat_query_rejects_default_graph_patterns_inside_filter_exists():
    sparql = (
        "SELECT ?s WHERE { "
        f"GRAPH <{GRAPH_A}> {{ ?anchor ?p ?o }} "
        "FILTER EXISTS { ?s ?p2 ?o2 } "
        "} LIMIT 10"
    )
    with patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.list_named_graphs",
        return_value=[(GRAPH_A, 10)],
    ), patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.execute_guarded_select"
    ) as execute:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ontology/chat/query",
                json={
                    "question": "Can a candidate hide default graph access in a filter?",
                    "selected_graph_uris": [GRAPH_A],
                    "candidate": {
                        "contract_version": "ontology-chat-query-v1",
                        "status": "query",
                        "sparql": sparql,
                    },
                },
            )

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "unscoped_default_graph_access"
    execute.assert_not_called()


def test_chat_query_applies_timeout_and_result_cap():
    bindings = [
        {
            "graph": {"type": "uri", "value": GRAPH_A},
            "subject": {"type": "uri", "value": NODE_A},
        },
        {
            "graph": {"type": "uri", "value": GRAPH_A},
            "subject": {"type": "uri", "value": NODE_B},
        },
    ]
    with patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.list_named_graphs",
        return_value=[(GRAPH_A, 10)],
    ), patch(
        "src.adapters.inbound.http.routes.ontology.plan_ontology_chat_query",
        return_value=_select_all_candidate(GRAPH_A, limit=1),
    ), patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.execute_guarded_select",
        return_value=bindings,
    ) as execute:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ontology/chat/query",
                json={
                    "question": "Return one row only.",
                    "selected_graph_uris": [GRAPH_A],
                    "row_limit": 1,
                    "timeout_seconds": 3,
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert len(body["rows"]) == 1
    assert body["guardrail_receipt"]["result_cap_applied"] is True
    assert body["guardrail_receipt"]["timeout_seconds"] == 3
    assert execute.call_args.kwargs["timeout_seconds"] == 3


def test_chat_query_returns_empty_overlay_when_rows_have_no_mapped_nodes():
    with patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.list_named_graphs",
        return_value=[(GRAPH_A, 10)],
    ), patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.execute_guarded_select",
        return_value=[
            {
                "graph": {"type": "uri", "value": GRAPH_A},
                "label": {"type": "literal", "value": "no mapped node"},
            }
        ],
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ontology/chat/query",
                json={
                    "question": "Show labels without node URIs.",
                    "selected_graph_uris": [GRAPH_A],
                },
            )

    assert response.status_code == 200
    overlay = response.json()["overlay_targets"][GRAPH_A]
    assert overlay["nodes"] == {}
    assert overlay["edges"] == {}


def test_chat_query_returns_llm_abstention_without_executing_fuseki():
    with patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.list_named_graphs",
        return_value=[(GRAPH_A, 10)],
    ), patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.execute_guarded_select"
    ) as execute:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ontology/chat/query",
                json={
                    "question": "What should happen if the model abstains?",
                    "selected_graph_uris": [GRAPH_A],
                    "candidate": {
                        "contract_version": "ontology-chat-query-v1",
                        "status": "abstain",
                        "rationale": "Insufficient grounding.",
                    },
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "abstained"
    assert body["rows"] == []
    assert body["guardrail_receipt"]["checks"]["llm_abstained"] is True
    execute.assert_not_called()


def test_path_resolve_returns_authoritative_and_projection_decision_path():
    case_run_uri = "http://inferra.ai/schema#session/case1"
    fact_uri = f"{case_run_uri}/fact/service_type"
    target_fact_uri = f"{case_run_uri}/fact/eligible"
    trace_uri = f"{case_run_uri}/semantic-question-strategy/0"
    projection_start = "http://inferra.ai/schema#rule/a/declaration/service_type"
    projection_middle = "http://inferra.ai/schema#rule/a/node/service_type_check"
    projection_target = "http://inferra.ai/schema#rule/a/node/eligible"

    case_context_rows = [
        {
            "graph": {"type": "uri", "value": FULL_GRAPH},
            "caseRun": {"type": "uri", "value": case_run_uri},
            "caseName": {"type": "literal", "value": "case1"},
            "targetNodeName": {"type": "literal", "value": "eligible"},
            "deterministicOutcomeRef": {"type": "uri", "value": target_fact_uri},
            "fact": {"type": "uri", "value": fact_uri},
            "factName": {"type": "literal", "value": "service type"},
            "factValue": {"type": "literal", "value": "warlike service"},
            "factSource": {"type": "literal", "value": "ASSERTED"},
            "factSession": {"type": "uri", "value": case_run_uri},
        },
        {
            "graph": {"type": "uri", "value": FULL_GRAPH},
            "caseRun": {"type": "uri", "value": case_run_uri},
            "caseName": {"type": "literal", "value": "case1"},
            "targetNodeName": {"type": "literal", "value": "eligible"},
            "deterministicOutcomeRef": {"type": "uri", "value": target_fact_uri},
            "fact": {"type": "uri", "value": target_fact_uri},
            "factName": {"type": "literal", "value": "eligible"},
            "factValue": {"type": "literal", "value": "True"},
            "factSource": {"type": "literal", "value": "INFERRED"},
            "factSession": {"type": "uri", "value": case_run_uri},
        },
    ]
    trace_rows = [
        {
            "graph": {"type": "uri", "value": FULL_GRAPH},
            "trace": {"type": "uri", "value": trace_uri},
            "traceType": {
                "type": "uri",
                "value": "http://inferra.ai/schema#SemanticQuestionStrategyTrace",
            },
            "questionName": {"type": "literal", "value": "service type"},
            "nodeName": {"type": "literal", "value": "service type check"},
            "generatedBy": {"type": "uri", "value": case_run_uri},
        }
    ]
    projection_node_rows = [
        {
            "graph": {"type": "uri", "value": GRAPH_A},
            "node": {"type": "uri", "value": projection_start},
            "name": {"type": "literal", "value": "service type"},
        },
        {
            "graph": {"type": "uri", "value": GRAPH_A},
            "node": {"type": "uri", "value": projection_middle},
            "name": {"type": "literal", "value": "service type check"},
        },
        {
            "graph": {"type": "uri", "value": GRAPH_A},
            "node": {"type": "uri", "value": projection_target},
            "name": {"type": "literal", "value": "eligible"},
        },
    ]
    projection_edge_rows = [
        {
            "graph": {"type": "uri", "value": GRAPH_A},
            "source": {"type": "uri", "value": projection_target},
            "predicate": {"type": "uri", "value": "http://inferra.ai/schema#andDependsOn"},
            "target": {"type": "uri", "value": projection_middle},
        },
        {
            "graph": {"type": "uri", "value": GRAPH_A},
            "source": {"type": "uri", "value": projection_middle},
            "predicate": {"type": "uri", "value": "http://inferra.ai/schema#dependencyProperty"},
            "target": {"type": "uri", "value": projection_start},
        },
    ]

    with patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.list_named_graphs",
        return_value=[(FULL_GRAPH, 20), (GRAPH_A, 12)],
    ), patch(
        "src.adapters.inbound.http.routes.ontology.FusekiAdapter.execute_guarded_select",
        side_effect=[
            case_context_rows,
            trace_rows,
            projection_node_rows,
            projection_edge_rows,
        ],
    ) as execute:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ontology/path/resolve",
                json={
                    "selected_graph_uris": [FULL_GRAPH, GRAPH_A],
                    "active_graph_uri": FULL_GRAPH,
                    "selected_row_index": 0,
                    "selected_row": {
                        "fact": {"type": "uri", "value": fact_uri},
                        "questionName": {"type": "literal", "value": "service type"},
                    },
                    "direction": "both",
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["selected_uri"] == fact_uri
    assert body["target_uri"] == target_fact_uri
    assert body["target_node_name"] == "eligible"
    assert body["authoritative_graph_uris"] == [FULL_GRAPH]
    assert body["structural_graph_uris"] == [GRAPH_A]
    assert {node["uri"] for node in body["nodes"]} >= {
        fact_uri,
        target_fact_uri,
        trace_uri,
        projection_start,
        projection_middle,
        projection_target,
    }
    relationship_types = {edge["relationship_type"] for edge in body["edges"]}
    assert "authoritative_case_fact" in relationship_types
    assert "authoritative_outcome" in relationship_types
    assert "semantic_trace" in relationship_types
    assert "projection_dependency" in relationship_types
    assert "projection_structure" in relationship_types
    assert execute.call_count == 4
