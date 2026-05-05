"""
HyperAdjacencyGraph Module.
Adjacency-list graph with cycle-protected back-propagation.

Provides the core data structure for INFERRA's dependency traversal,
replacing the legacy 2D dependency matrix with a sparse, name-based
adjacency representation. Back-propagation uses BFS with visited-set
and max-iteration guards to detect cyclic dependencies at runtime.

Implements DependencyGraphPort using primitive types for the port contract,
while also exposing a richer typed API via add_dependency_group() with
DependencyType enum and DependencyGroup NamedTuple.

Phase 2.5 (WS-7): Added _edge_types reverse index, _nodes NodeRecord
storage, and _name_to_id/_id_to_name bidirectional mapping for O(1)
lookups. Implements register_node(), edges(), and overrides default
methods with efficient implementations.
"""

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterator, List, Optional, Set, Tuple

from src.domain.graph.dependency_group import DependencyGroup
from src.domain.graph.dependency_type import DependencyType
from src.ports.dependency_graph_port import DependencyGraphPort
from src.shared.loggers import Logger

_logger: Logger = Logger.get_logger(__name__)


class CyclicGraphError(RuntimeError):
    """Raised when back-propagation detects a likely cyclic dependency."""
    pass


@dataclass(frozen=True)
class NodeRecord:
    """
    Immutable metadata for a node stored on the graph.

    Subsumes Phase 2's NodeOrigin fields (imported, import_depth)
    and adds stable_id, module, and import_namespace provenance.
    """
    name: str
    stable_id: str = ""
    runtime_id: int = -1
    module: str = ""
    import_namespace: str = ""
    import_version: str = ""
    imported: bool = False
    import_depth: int = 0


class HyperAdjacencyGraph(DependencyGraphPort):
    """
    Sparse, name-based adjacency graph with hyper-edge support.

    Children are stored as lists of DependencyGroup tuples (immutable
    NamedTuple), enabling multi-child edges with shared dependency types.
    Parents are stored as a reverse-lookup dict for efficient back-propagation.

    Topological sort cache is invalidated on every mutation.

    Phase 2.5 indices:
    - _edge_types: O(1) per-edge dep_type lookup
    - _nodes: explicit NodeRecord storage (subsumes NodeOrigin)
    - _name_to_id / _id_to_name: bidirectional runtime ID mapping
    """

    def __init__(self) -> None:
        self._children: Dict[str, Tuple[DependencyGroup, ...]] = {}
        self._parents: Dict[str, Set[str]] = {}
        self._topo_cache: Optional[Tuple[str, ...]] = None
        self._edge_types: Dict[Tuple[str, str], int] = {}
        self._nodes: Dict[str, NodeRecord] = {}
        self._name_to_id: Dict[str, int] = {}
        self._id_to_name: Dict[int, str] = {}
        self._next_id: int = 0

    def register_node(self, name: str, metadata: Optional[dict] = None) -> int:
        """
        Register a node with optional metadata, returning a runtime integer ID.

        If the node already exists, returns the existing ID and updates
        metadata if provided.
        """
        if name in self._name_to_id:
            existing_id = self._name_to_id[name]
            if metadata is not None:
                existing = self._nodes[name]
                self._nodes[name] = NodeRecord(
                    name=name,
                    stable_id=metadata.get("stable_id", existing.stable_id),
                    runtime_id=existing_id,
                    module=metadata.get("module", existing.module),
                    import_namespace=metadata.get("import_namespace", existing.import_namespace),
                    import_version=metadata.get("import_version", existing.import_version),
                    imported=metadata.get("imported", existing.imported),
                    import_depth=metadata.get("import_depth", existing.import_depth),
                )
            return existing_id

        requested_id = metadata.get("runtime_id") if metadata is not None else None
        if (
            isinstance(requested_id, int)
            and requested_id >= 0
            and requested_id not in self._id_to_name
        ):
            node_id = requested_id
        else:
            while self._next_id in self._id_to_name:
                self._next_id += 1
            node_id = self._next_id
        self._next_id = max(self._next_id, node_id + 1)
        self._name_to_id[name] = node_id
        self._id_to_name[node_id] = name

        if metadata is not None:
            self._nodes[name] = NodeRecord(
                name=name,
                stable_id=metadata.get("stable_id", ""),
                runtime_id=node_id,
                module=metadata.get("module", ""),
                import_namespace=metadata.get("import_namespace", ""),
                import_version=metadata.get("import_version", ""),
                imported=metadata.get("imported", False),
                import_depth=metadata.get("import_depth", 0),
            )
        else:
            self._nodes[name] = NodeRecord(name=name, runtime_id=node_id)

        self._topo_cache = None
        return node_id

    def get_node_record(self, name: str) -> Optional[NodeRecord]:
        """Return the NodeRecord for a node, or None if not registered."""
        return self._nodes.get(name)

    def find_nodes_by_module(self, module: str) -> List[NodeRecord]:
        """Return all NodeRecords whose module matches."""
        return [r for r in self._nodes.values() if r.module == module]

    def find_nodes_by_namespace(self, namespace: str) -> List[NodeRecord]:
        """Return all NodeRecords whose import_namespace matches."""
        return [r for r in self._nodes.values() if r.import_namespace == namespace]

    # -------------------------------------------------------------------------
    # Public API: Mutation
    # -------------------------------------------------------------------------

    def add_dependency_group(
        self,
        parent: str,
        dep_type: DependencyType = DependencyType.AND,
        children: Optional[Set[str]] = None,
    ) -> None:
        """
        Add a dependency group from parent to a set of children.

        Write-time bitmask merge: if child already exists for this parent
        with a different dep_type, the bitmasks are ORed together in
        _edge_types and the children groups are rebuilt.

        Args:
            parent: Parent node name
            dep_type: Dependency type (enum or int from port contract)
            children: Set of child node names
        """
        if children is None:
            children = set()
        if isinstance(dep_type, int) and not isinstance(dep_type, DependencyType):
            dep_type = DependencyType(dep_type)

        for child in children:
            key = (parent, child)
            existing_dep = self._edge_types.get(key)
            if existing_dep is not None:
                merged = existing_dep | int(dep_type)
                self._edge_types[key] = merged
            else:
                self._edge_types[key] = int(dep_type)

        for child in children:
            self._parents.setdefault(child, set()).add(parent)

        self._rebuild_groups_for(parent)
        self._topo_cache = None

    def remove_node(self, name: str) -> None:
        """Remove a node and all incoming/outgoing edges."""
        child_names = {
            child
            for (parent, child) in self._edge_types
            if parent == name
        }
        for child in child_names:
            self._edge_types.pop((name, child), None)
            parents = self._parents.get(child)
            if parents is not None:
                parents.discard(name)
                if not parents:
                    self._parents.pop(child, None)

        parent_names = set(self._parents.get(name, set()))
        for parent in parent_names:
            self._edge_types.pop((parent, name), None)
            self._rebuild_groups_for(parent)

        self._children.pop(name, None)
        self._parents.pop(name, None)
        self._nodes.pop(name, None)
        runtime_id = self._name_to_id.pop(name, None)
        if runtime_id is not None:
            self._id_to_name.pop(runtime_id, None)
        self._topo_cache = None

    def _rebuild_groups_for(self, parent: str) -> None:
        """Rebuild _children groups for a parent from _edge_types."""
        child_by_type: Dict[int, set] = {}
        for (p, child), dep_val in self._edge_types.items():
            if p == parent:
                child_by_type.setdefault(dep_val, set()).add(child)
        self._children[parent] = tuple(
            DependencyGroup(DependencyType(dt), frozenset(ch))
            for dt, ch in child_by_type.items()
        )

    # -------------------------------------------------------------------------
    # Public API: Queries (DependencyGraphPort contract — primitive types)
    # -------------------------------------------------------------------------

    def get_parent_edges(self, node_name: str) -> Set[str]:
        """Return the set of parent node names for the given node."""
        return set(self._parents.get(node_name, set()))

    def get_child_groups(self, node_name: str) -> Tuple[Tuple[int, Tuple[str, ...]], ...]:
        """
        Return dependency groups as primitive tuples (port contract).

        Each group is (dep_type: int, children: tuple of str).
        """
        groups = self._children.get(node_name, ())
        return tuple(
            (int(g.dep_type), tuple(sorted(g.children)))
            for g in groups
        )

    # -------------------------------------------------------------------------
    # Public API: Rich typed queries (domain-level convenience)
    # -------------------------------------------------------------------------

    def get_typed_child_groups(self, node_name: str) -> Tuple[DependencyGroup, ...]:
        """Return DependencyGroup NamedTuples for domain-level consumers."""
        return self._children.get(node_name, ())

    def has_node(self, node_name: str) -> bool:
        """Check whether a node name exists in the graph (as parent or child or registered)."""
        return node_name in self._children or node_name in self._parents or node_name in self._nodes

    def all_node_names(self) -> Set[str]:
        """Return all node names known to the graph."""
        names: Set[str] = set(self._children.keys())
        names.update(self._parents.keys())
        names.update(self._nodes.keys())
        return names

    # -------------------------------------------------------------------------
    # Public API: Default method overrides (O(1) implementations)
    # -------------------------------------------------------------------------

    def get_dependency_type(self, parent: str, child: str) -> int:
        """Return dep_type bitmask for a specific edge. O(1) via _edge_types."""
        return self._edge_types.get((parent, child), -1)

    def has_children_of_type(self, node_name: str, type_mask: int) -> bool:
        """Check if node has any children matching a bitmask. O(groups) with early exit."""
        for group in self._children.get(node_name, ()):
            if int(group.dep_type) & type_mask == type_mask:
                return True
        return False

    def lookup_by_id(self, runtime_id: int) -> Optional[str]:
        """Look up node name by runtime integer ID. O(1) via _id_to_name."""
        return self._id_to_name.get(runtime_id)

    def lookup_by_name(self, name: str) -> Optional[int]:
        """Look up runtime integer ID by node name. O(1) via _name_to_id."""
        return self._name_to_id.get(name)

    def subgraph(self, node_names: Set[str]) -> 'HyperAdjacencyGraph':
        """
        Extract an induced subgraph preserving nodes, records, and dep types.

        This keeps isolated nodes and NodeRecord provenance, which the port
        default cannot do without knowing the concrete graph metadata model.
        """
        result = HyperAdjacencyGraph()
        for name in sorted(node_names):
            if not self.has_node(name):
                continue
            record = self.get_node_record(name)
            if record is not None:
                result.register_node(
                    name,
                    {
                        "stable_id": record.stable_id,
                        "runtime_id": record.runtime_id,
                        "module": record.module,
                        "import_namespace": record.import_namespace,
                        "import_version": record.import_version,
                        "imported": record.imported,
                        "import_depth": record.import_depth,
                    },
                )
            else:
                result.register_node(name)

        for parent, child, dep_type in self.edges():
            if parent in node_names and child in node_names:
                result.add_dependency_group(parent, dep_type, {child})
        return result

    # -------------------------------------------------------------------------
    # Public API: Edge iteration
    # -------------------------------------------------------------------------

    def edges(self) -> Iterator[Tuple[str, str, int]]:
        """
        Iterate over all edges as (parent, child, dep_type) triples.

        Uses _edge_types for O(E) iteration without scanning groups.
        """
        for (parent, child), dep_type in self._edge_types.items():
            yield (parent, child, dep_type)

    # -------------------------------------------------------------------------
    # Public API: Back-propagation (BFS with cycle guard)
    # -------------------------------------------------------------------------

    def back_propagate(self, changed_node: str, max_steps: int = 0) -> Deque[str]:
        """
        BFS back-propagation from a changed node to all affected parents.

        Includes cyclic-graph protection: a visited set prevents re-visiting
        nodes, and a max-iteration guard raises CyclicGraphError when the
        traversal exceeds the limit.

        Args:
            changed_node: Name of the node that changed
            max_steps: Maximum BFS steps (0 = auto-compute from graph size)

        Returns:
            Deque of unique parent node names in BFS visit order

        Raises:
            CyclicGraphError: If traversal exceeds max_steps
        """
        if max_steps == 0:
            max_steps = max(len(self._parents) * 2, 1)

        visited: Set[str] = set()
        queued: Set[str] = {changed_node}
        queue: Deque[str] = deque([changed_node])
        evaluated: Deque[str] = deque()
        steps = 0

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            steps += 1

            if steps > max_steps:
                raise CyclicGraphError(
                    f"Back-propagation exceeded {max_steps} steps — "
                    f"possible cyclic graph"
                )

            for parent_name in self.get_parent_edges(current):
                if parent_name not in visited and parent_name not in queued:
                    queued.add(parent_name)
                    queue.append(parent_name)
                    evaluated.append(parent_name)

        return evaluated

    # -------------------------------------------------------------------------
    # Public API: Topological sort (Kahn's algorithm)
    # -------------------------------------------------------------------------

    def topological_sort(self) -> Tuple[str, ...]:
        """
        Return nodes in topological order using Kahn's algorithm.

        Result is cached until the next mutation. Returns an empty tuple
        if the graph contains a cycle.

        Returns:
            Tuple of node names in topological order
        """
        if self._topo_cache is not None:
            return self._topo_cache

        all_names = self.all_node_names()
        in_degree: Dict[str, int] = {name: 0 for name in all_names}
        for name in all_names:
            for group in self.get_typed_child_groups(name):
                for child in group.children:
                    if child in in_degree:
                        in_degree[child] += 1

        queue: Deque[str] = deque(
            name for name, deg in in_degree.items() if deg == 0
        )
        result: list = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for group in self.get_typed_child_groups(node):
                for child in group.children:
                    if child in in_degree:
                        in_degree[child] -= 1
                        if in_degree[child] == 0:
                            queue.append(child)

        if len(result) != len(all_names):
            _logger.error("Cyclic graph detected during topological sort")
            self._topo_cache = ()
            return ()

        self._topo_cache = tuple(result)
        return self._topo_cache

    # -------------------------------------------------------------------------
    # Public API: Utility
    # -------------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all nodes and edges from the graph."""
        self._children.clear()
        self._parents.clear()
        self._topo_cache = None
        self._edge_types.clear()
        self._nodes.clear()
        self._name_to_id.clear()
        self._id_to_name.clear()
        self._next_id = 0

    def __len__(self) -> int:
        return len(self.all_node_names())

    def __repr__(self) -> str:
        return (
            f"HyperAdjacencyGraph(nodes={len(self)}, "
            f"edges={len(self._edge_types)})"
        )
