"""
NodeOrigin — provenance metadata for merged nodes.

Attached to every node in a merged NodeSet to trace which module
contributed it, whether it was imported or local, and at what depth
in the import chain it was discovered.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NodeOrigin:
    """
    Immutable provenance record for a node in a merged rule set.

    Attributes:
        module: Name of the rule module that defined this node
        imported: True if the node came from an imported module
        depth: Import chain depth (0 = local, 1 = directly imported, etc.)
    """
    module: str
    imported: bool
    depth: int

    def is_local(self) -> bool:
        return not self.imported

    def is_direct_import(self) -> bool:
        return self.imported and self.depth == 1
