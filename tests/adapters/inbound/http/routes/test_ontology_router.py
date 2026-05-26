from unittest.mock import patch

from fastapi.testclient import TestClient

from src.main import app


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
