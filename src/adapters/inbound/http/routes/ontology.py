from fastapi import APIRouter, Query

from src.adapters.inbound.http.schemas.ontology import (
    FusekiGraphListResponse,
    FusekiGraphResponse,
)
from src.adapters.outbound.ontology.fuseki_adapter import INF_NS, FusekiAdapter


router = APIRouter(prefix="/api/v1/ontology", tags=["ontology"])

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


@router.get("/fuseki/graphs", response_model=FusekiGraphListResponse)
async def list_fuseki_named_graphs() -> FusekiGraphListResponse:
    graphs = [
        {"uri": uri, "triple_count": triple_count}
        for uri, triple_count in FusekiAdapter.list_named_graphs()
    ]
    return FusekiGraphListResponse(graphs=graphs, total_count=len(graphs))


@router.get("/fuseki/graph", response_model=FusekiGraphResponse)
async def get_fuseki_named_graph(
    graph_uri: str = Query(..., min_length=1),
    offset: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=5000),
) -> FusekiGraphResponse:
    triples = FusekiAdapter.get_named_graph_triples(graph_uri, offset=offset, limit=limit)
    graph = _ontology_graph_from_triples(triples)
    return FusekiGraphResponse(
        graph_uri=graph_uri,
        triple_count=len(triples),
        triples=[
            {"subject": subject, "predicate": predicate, "object": obj}
            for subject, predicate, obj in triples
        ],
        nodes=graph["nodes"],
        edges=graph["edges"],
        offset=offset,
        limit=limit,
    )


def _ontology_graph_from_triples(triples: list[tuple[str, str, str]]) -> dict:
    node_map: dict[str, dict] = {}
    edges: list[dict[str, str]] = []

    def ensure_node(uri: str) -> dict:
        return node_map.setdefault(uri, {"uri": uri, "name": None, "types": []})

    for subject, predicate, obj in triples:
        ensure_node(subject)
        if predicate == f"{INF_NS}name":
            node_map[subject]["name"] = obj
            continue
        if predicate == RDF_TYPE:
            node = ensure_node(subject)
            if obj not in node["types"]:
                node["types"].append(obj)
            continue
        if obj.startswith(("http://", "https://", "urn:")):
            ensure_node(obj)
            edges.append({"subject": subject, "predicate": predicate, "object": obj})

    return {"nodes": list(node_map.values()), "edges": edges}
