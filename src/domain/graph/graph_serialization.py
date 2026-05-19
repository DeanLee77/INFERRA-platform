"""
Graph Edge-List Serialization Module.
Serializes and deserializes HyperAdjacencyGraph as edge-list JSON.

Phase 2.5 (WS-3): New persistence format replacing dense matrix storage.
Simple, human-readable, easy to diff. Reconstruct HyperAdjacencyGraph
at load time.
"""

import json
from typing import Any, Dict, List, Optional

from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph, NodeRecord
from src.infrastructure.logging_config import get_logger

_logger = get_logger(__name__)

SCHEMA_VERSION = 1


def serialize_graph(graph: HyperAdjacencyGraph) -> str:
    """
    Serialize a HyperAdjacencyGraph to a JSON edge-list string.

    Format:
    {
        "schema_version": 1,
        "nodes": [
            {"name": "A", "stable_id": "abc", "runtime_id": 0, "module": "rules", ...},
            ...
        ],
        "edges": [
            {"parent": "A", "child": "B", "dep_type": 72},
            ...
        ]
    }
    """
    nodes: List[Dict[str, Any]] = []
    for name in graph.all_node_names():
        record = graph.get_node_record(name)
        if record is not None:
            nodes.append({
                "name": record.name,
                "stable_id": record.stable_id,
                "runtime_id": record.runtime_id,
                "module": record.module,
                "import_namespace": record.import_namespace,
                "import_version": record.import_version,
                "imported": record.imported,
                "import_depth": record.import_depth,
            })
        else:
            rid = graph.lookup_by_name(name)
            nodes.append({"name": name, "runtime_id": rid if rid is not None else -1})

    edges: List[Dict[str, Any]] = []
    for parent, child, dep_type in graph.edges():
        edges.append({"parent": parent, "child": child, "dep_type": dep_type})

    payload = {
        "schema_version": SCHEMA_VERSION,
        "nodes": nodes,
        "edges": edges,
    }
    return json.dumps(payload, indent=2)


def deserialize_graph(data: str) -> HyperAdjacencyGraph:
    """
    Deserialize a JSON edge-list string into a HyperAdjacencyGraph.

    Args:
        data: JSON string from serialize_graph()

    Returns:
        Reconstructed HyperAdjacencyGraph
    """
    payload = json.loads(data)
    schema_version = payload.get("schema_version", 0)
    if schema_version > SCHEMA_VERSION:
        _logger.warning(f"Graph schema version {schema_version} > {SCHEMA_VERSION}; attempting load")

    graph = HyperAdjacencyGraph()

    for node_data in payload.get("nodes", []):
        name = node_data["name"]
        metadata = {k: v for k, v in node_data.items() if k != "name" and v is not None and v != -1 and v != ""}
        graph.register_node(name, metadata)

    for edge_data in payload.get("edges", []):
        parent = edge_data["parent"]
        child = edge_data["child"]
        dep_type = edge_data["dep_type"]
        graph.add_dependency_group(parent, dep_type, {child})

    return graph
