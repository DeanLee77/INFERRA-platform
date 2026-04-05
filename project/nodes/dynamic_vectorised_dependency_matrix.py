"""
Dynamic Vectorised Dependency Matrix Module.
High-performance dependency matrix using NumPy for vectorised operations.
Implements access levels and strong typing where appropriate.
"""

import numpy as np
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Any
from .dependency_type import DependencyType


class DynamicVectorisedDependencyMatrix:
    """
    DynamicVectorisedDependencyMatrix provides vectorised per-node adjacency lists.
    
    Features:
    - add_dependency() works anytime (before/after build)
    - Automatic re-indexing when new nodes (virtual nodes, iterate nodes) are inserted
    - All queries use pure NumPy boolean indexing → extremely fast
    - Sparse memory usage (only real edges stored)
    - Perfect for virtual node creation during parsing and IterateLine expansion
    
    Access Levels:
    - Public: API methods for external use
    - Protected: Internal helpers (single underscore)
    - Private: Internal state (double underscore)
    """
    
    # -------------------------------------------------------------------------
    # Private Access Level: Instance Variables (Name Mangling)
    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        """
        Public Constructor: Initializes DynamicVectorisedDependencyMatrix.
        """
        # Private instance variables (initialized in __init__ to avoid shared state)
        self.__children: Dict[int, List[int]] = defaultdict(list)
        self.__dep_types: Dict[int, List[int]] = defaultdict(list)
        self.__parents: Dict[int, List[int]] = defaultdict(list)  # reverse edges

        # Vectorised NumPy structures (built lazily)
        self.__vec_children: Dict[int, np.ndarray] = {}
        self.__vec_dep_types: Dict[int, np.ndarray] = {}

        self.__max_node_id: int = -1
        self.__needs_rebuild: bool = False

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Dependency Management)
    # -------------------------------------------------------------------------
    def add_dependency(self, parent_id: int, child_id: int, dep_type: int) -> None:
        """
        Public API: Add a dependency edge. Safe to call at any time during parsing.
        
        Args:
            parent_id: Parent node ID (must be >= 0)
            child_id: Child node ID (must be >= 0 and != parent_id)
            dep_type: Dependency type integer (bitmask from DependencyType)
            
        Raises:
            ValueError: If IDs are negative, equal, or dep_type is invalid
        """
        if parent_id < 0 or child_id < 0:
            raise ValueError("Node IDs cannot be negative")
        if parent_id == child_id:
            raise ValueError("A node cannot be a dependency of itself")
            
        self.__children[parent_id].append(child_id)
        self.__dep_types[parent_id].append(dep_type)
        self.__parents[child_id].append(parent_id)

        self.__max_node_id = max(self.__max_node_id, parent_id, child_id)
        self.__needs_rebuild = True

    def build(self) -> None:
        """
        Public API: Convert Python lists to NumPy arrays for vectorised operations.
        Called automatically on first query or manually after bulk changes.
        """
        if not self.__needs_rebuild:
            return

        for pid in list(self.__children.keys()):
            # Convert to int32 for memory efficiency and NumPy compatibility
            self.__vec_children[pid] = np.array(self.__children[pid], dtype=np.int32)
            self.__vec_dep_types[pid] = np.array(self.__dep_types[pid], dtype=np.int32)

        self.__needs_rebuild = False

    def clear(self) -> None:
        """
        Public API: Resets the matrix to an empty state.
        Useful for re-parsing or testing.
        """
        self.__children.clear()
        self.__dep_types.clear()
        self.__parents.clear()
        self.__vec_children.clear()
        self.__vec_dep_types.clear()
        self.__max_node_id = -1
        self.__needs_rebuild = False

    # -------------------------------------------------------------------------
    # Protected Access Level: Internal Helpers (Single Underscore)
    # -------------------------------------------------------------------------
    def _ensure_built(self) -> None:
        """
        Protected Helper: Ensures NumPy arrays are built before queries.
        """
        if self.__needs_rebuild:
            self.build()

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Vectorised Queries)
    # -------------------------------------------------------------------------
    def get_to_child_dependency_list(self, node_id: int) -> List[int]:
        """
        Public API: Gets list of child node IDs for a given node.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            List of child node IDs
        """
        self._ensure_built()
        arr = self.__vec_children.get(node_id)
        return arr.tolist() if arr is not None else []

    def get_and_to_child_dependency_list(self, node_id: int) -> List[int]:
        """
        Public API: Gets list of AND-type child node IDs.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            List of AND-type child node IDs
        """
        self._ensure_built()
        types_arr = self.__vec_dep_types.get(node_id)
        if types_arr is None:
            return []
        mask = (types_arr & DependencyType.get_and()) == DependencyType.get_and()
        return self.__vec_children[node_id][mask].tolist()

    def get_or_to_child_dependency_list(self, node_id: int) -> List[int]:
        """
        Public API: Gets list of OR-type child node IDs.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            List of OR-type child node IDs
        """
        self._ensure_built()
        types_arr = self.__vec_dep_types.get(node_id)
        if types_arr is None:
            return []
        mask = (types_arr & DependencyType.get_or()) == DependencyType.get_or()
        return self.__vec_children[node_id][mask].tolist()

    def get_mandatory_to_child_dependency_list(self, node_id: int) -> List[int]:
        """
        Public API: Gets list of MANDATORY-type child node IDs.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            List of MANDATORY-type child node IDs
        """
        self._ensure_built()
        types_arr = self.__vec_dep_types.get(node_id)
        if types_arr is None:
            return []
        mask = (types_arr & DependencyType.get_mandatory()) == DependencyType.get_mandatory()
        return self.__vec_children[node_id][mask].tolist()

    def get_from_parent_dependency_list(self, node_id: int) -> List[int]:
        """
        Public API: All parents that have this node as child.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            List of parent node IDs
        """
        return self.__parents.get(node_id, [])

    def has_mandatory_child_node(self, node_id: int) -> bool:
        """
        Public API: Checks if node has mandatory child nodes.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            True if has mandatory children, False otherwise
        """
        self._ensure_built()
        types_arr = self.__vec_dep_types.get(node_id)
        if types_arr is None:
            return False
        mask = (types_arr & DependencyType.get_mandatory()) == DependencyType.get_mandatory()
        return bool(np.any(mask))

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Dynamic Node Support)
    # -------------------------------------------------------------------------
    def get_next_node_id(self) -> int:
        """
        Public API: Returns next safe node ID for virtual nodes.
        
        Returns:
            Next available node ID
        """
        return self.__max_node_id + 1

    def add_new_node(self, node_id: int) -> None:
        """
        Public API: Explicitly register a new node ID (useful for virtual nodes).
        
        Args:
            node_id: Node ID to register
        """
        if node_id > self.__max_node_id:
            self.__max_node_id = node_id
            self.__needs_rebuild = True

    # -------------------------------------------------------------------------
    # Public Access Level: API Methods (Utility & Debugging)
    # -------------------------------------------------------------------------
    def get_dependency_vector(self, node_id: int) -> np.ndarray:
        """
        Public API: Return structured array of (child_id, dep_type) for debugging.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            NumPy structured array with fields 'child_id' and 'dep_type'
        """
        self._ensure_built()
        if node_id not in self.__vec_children:
            return np.empty(0, dtype=[('child_id', 'i4'), ('dep_type', 'i4')])
        return np.stack((self.__vec_children[node_id], self.__vec_dep_types[node_id]), axis=1)

    @property
    def node_count(self) -> int:
        """
        Public API: Returns the total number of unique nodes registered.
        
        Returns:
            Total node count (0 if empty)
        """
        return max(self.__max_node_id + 1, 0)

    def __len__(self) -> int:
        """
        Public API: Returns the total number of nodes.
        
        Returns:
            Total node count
        """
        return self.node_count

    def __contains__(self, node_id: int) -> bool:
        """
        Public API: Checks if a node ID exists in the matrix.
        
        Args:
            node_id: Node ID to check
            
        Returns:
            True if node exists, False otherwise
        """
        return (0 <= node_id <= self.__max_node_id)

    def __repr__(self) -> str:
        """
        Public API: String representation of the object.
        
        Returns:
            Summary string for debugging
        """
        self._ensure_built()
        total_edges = sum(len(arr) for arr in self.__vec_children.values())
        return (
            f"DynamicVectorisedDependencyMatrix("
            f"nodes={self.node_count}, "
            f"edges={total_edges}, "
            f"built={not self.__needs_rebuild})"
        )