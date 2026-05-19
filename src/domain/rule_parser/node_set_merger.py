"""
NodeSetMerger — merges imported NodeSets with local rules.

Merge rules:
- Name collision: local node wins over imported node (local override).
- ID collision: module-qualified IDs from generate_node_id() prevent this.
- Ordering: imported nodes prepended before local nodes in topological order.
- Dependency groups: merged dependency groups are unioned; duplicate edges deduplicated.
- NodeOrigin: every merged node gets {module, imported, depth} metadata.

Phase 2.5 (WS-2): Merges at the graph level with write-time bitmask OR.
Legacy matrices are derived from the merged graph on demand.
"""

from __future__ import annotations

from copy import copy
from typing import Dict, List, Optional, Set

import structlog

from src.domain.graph.hyper_adjacency_graph import HyperAdjacencyGraph
from src.domain.imports.node_origin import NodeOrigin
from src.domain.nodes.node import Node
from src.domain.nodes.node_id_utils import (
    CANONICAL_NODE_KEY_SEPARATOR,
    canonical_node_key,
)
from src.domain.nodes.node_set import NodeSet

log = structlog.get_logger()


class NodeSetMerger:
    """Merges imported NodeSets with local rules."""

    @staticmethod
    def merge(
        local_node_set: NodeSet,
        imported_node_sets: List[NodeSet],
        imported_origins: Optional[Dict[str, NodeOrigin]] = None,
        rule_name: str = "__local__",
    ) -> NodeSet:
        merged = NodeSet()
        merged.set_node_set_name(local_node_set.get_node_set_name() or rule_name)

        merged_graph = HyperAdjacencyGraph()
        merged.set_graph(merged_graph)

        seen_names: Set[str] = set()

        for idx, imported_ns in enumerate(imported_node_sets):
            ns_name = imported_ns.get_node_set_name() or f"__import_{idx}__"
            origin = None
            if imported_origins and ns_name in imported_origins:
                origin = imported_origins[ns_name]
            if origin is None:
                origin = NodeOrigin(module=ns_name, imported=True, depth=1)

            for node in imported_ns.get_sorted_node_list():
                name = _canonical_name(node.get_node_name(), origin)
                if name in seen_names:
                    log.debug("import_name_collision_skipped", node_name=name, source=ns_name)
                    continue
                merged.add_node(
                    _node_with_graph_name(node, name),
                    _origin_metadata(node, origin),
                )
                seen_names.add(name)
                log.debug("node_merged", node_name=name, source=ns_name)

        for node in local_node_set.get_sorted_node_list():
            name = node.get_node_name()
            if name in seen_names:
                merged.remove_node_by_name(name)
                log.debug("node_override_local_wins", node_name=name)
            origin = NodeOrigin(module=rule_name, imported=False, depth=0)
            merged.add_node(node, _origin_metadata(node, origin))
            seen_names.add(name)

        _merge_graphs(
            merged.get_graph(),
            local_node_set,
            imported_node_sets,
            imported_origins,
        )

        merged.set_input_dictionary(
            _merge_dicts(
                [ns.get_input_dictionary() for ns in imported_node_sets]
                + [local_node_set.get_input_dictionary()]
            )
        )
        merged.set_fact_dictionary(
            _merge_dicts(
                [ns.get_fact_dictionary() for ns in imported_node_sets]
                + [local_node_set.get_fact_dictionary()]
            )
        )

        if local_node_set.get_default_goal_node() is not None:
            goal_name = local_node_set.get_default_goal_node().get_node_name()
            merged.set_default_goal_node(goal_name)

        log.info(
            "node_set_merged",
            rule_name=rule_name,
            imported_count=len(imported_node_sets),
            total_nodes=len(merged.get_node_dictionary()),
            graph_merge=True,
        )
        return merged


def _origin_metadata(node: Node, origin: Optional[NodeOrigin] = None) -> dict:
    """Build graph NodeRecord metadata from a Node + NodeOrigin."""
    metadata: dict = {}
    runtime_id = getattr(node, "_node_id", None)
    if isinstance(runtime_id, int):
        metadata["runtime_id"] = runtime_id
    if node.get_stable_node_id() is not None:
        metadata["stable_id"] = node.get_stable_node_id()
    if origin is not None:
        metadata["module"] = origin.module
        metadata["imported"] = origin.imported
        metadata["import_depth"] = origin.depth
        metadata["import_namespace"] = (
            getattr(origin, "import_namespace", "") or origin.module if origin.imported else ""
        )
        metadata["import_version"] = getattr(origin, "import_version", "")
    return metadata


def _merge_graphs(
    target: HyperAdjacencyGraph,
    local_node_set: NodeSet,
    imported_node_sets: List[NodeSet],
    imported_origins: Optional[Dict[str, NodeOrigin]] = None,
) -> None:
    """Merge edges from all input graphs into the target graph.

    Uses write-time bitmask OR via add_dependency_group() — identical
    The graph performs bitmask OR when duplicate edges are added.
    """
    for idx, imported_ns in enumerate(imported_node_sets):
        ns_name = imported_ns.get_node_set_name() or f"__import_{idx}__"
        origin = imported_origins.get(ns_name) if imported_origins else None
        if origin is None:
            origin = NodeOrigin(module=ns_name, imported=True, depth=1)
        src = imported_ns.get_graph()
        if src is not None:
            for parent, child, dep_type in src.edges():
                target.add_dependency_group(
                    _canonical_name(parent, origin),
                    dep_type,
                    {_canonical_name(child, origin)},
                )

    local_graph = local_node_set.get_graph()
    if local_graph is not None:
        for parent, child, dep_type in local_graph.edges():
            target.add_dependency_group(parent, dep_type, {child})


def _merge_dicts(dicts: List[Dict]) -> Dict:
    """Merge dictionaries right-to-left (later values override earlier)."""
    result: Dict = {}
    for d in dicts:
        result.update(d)
    return result


def _canonical_name(name: str, origin: NodeOrigin) -> str:
    """Return the graph key for a node at a merge boundary."""
    if not origin.imported:
        return name
    if CANONICAL_NODE_KEY_SEPARATOR in str(name):
        return name
    return canonical_node_key(name, origin.module)


def _node_with_graph_name(node: Node, graph_name: str) -> Node:
    """Shallow-copy a node and give the copy its canonical graph key."""
    cloned = copy(node)
    cloned._node_name = graph_name
    cloned._node_id = None
    cloned._node_unique_id = -1
    return cloned
