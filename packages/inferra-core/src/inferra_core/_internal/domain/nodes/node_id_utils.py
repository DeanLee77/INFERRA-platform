import hashlib
import warnings
from typing import Dict, Optional, Set

CANONICAL_NODE_KEY_SEPARATOR = "::"


def canonical_node_key(node_name: str, origin_module: str = "") -> str:
    """Return the runtime graph key for a node.

    Local nodes use their raw node name. Imported nodes use a qualified
    module/name key, for example ``common_rules@2.1.0::eligibility``.
    This key is separate from ``stable_id``, which remains a compatibility
    and persistence lookup value.
    """
    normalized_name = str(node_name).strip()
    normalized_origin = str(origin_module or "").strip()
    if not normalized_origin:
        return normalized_name
    prefix = f"{normalized_origin}{CANONICAL_NODE_KEY_SEPARATOR}"
    if normalized_name.startswith(prefix):
        return normalized_name
    return f"{prefix}{normalized_name}"


def unqualified_node_key(node_key: str) -> str:
    """Return the raw node name from a canonical graph key."""
    return str(node_key).rsplit(CANONICAL_NODE_KEY_SEPARATOR, 1)[-1]


class NodeIdContext:
    """Caller-owned collision tracker for one deterministic parse session."""

    def __init__(self) -> None:
        self._active_ids: Dict[str, str] = {}

    def generate_node_id(
        self,
        module_path: str,
        rule_name: str,
        variable_name: str,
        normalized_text: str = "",
        parent_module_path: str = "",
        import_namespace: str = "",
        line_number: Optional[int] = None,
    ) -> str:
        content = f"{module_path}:{rule_name}:{variable_name}:{normalized_text}:{parent_module_path}:{import_namespace}"
        base_id = hashlib.sha256(content.encode()).hexdigest()[:16]

        existing = self._active_ids.get(base_id)
        if existing is None:
            self._active_ids[base_id] = content
            return base_id
        if existing == content:
            return base_id

        counter = 1
        while True:
            candidate = f"{base_id}:{counter}"
            existing = self._active_ids.get(candidate)
            if existing is None:
                self._active_ids[candidate] = content
                return candidate
            if existing == content:
                return candidate
            counter += 1

    def reset(self) -> None:
        self._active_ids.clear()

    def validate_no_existing_collisions(self, persisted_session_ids: Set[str]) -> None:
        overlap = set(self._active_ids.keys()) & persisted_session_ids
        if overlap:
            raise ValueError(f"Hash ID collision with persisted sessions: {overlap}")


def generate_node_id(
    module_path: str,
    rule_name: str,
    variable_name: str = "",
    normalized_text: str = "",
    parent_module_path: str = "",
    import_namespace: str = "",
    line_number: Optional[int] = None,
    *,
    context: Optional[NodeIdContext] = None,
) -> str:
    """Deterministic 16-char hex ID (64-bit entropy).

    Same inputs always return the same ID within a parse session. Two distinct
    inputs that share the same 16-char SHA-256 prefix get a monotonic counter
    suffix appended so node identity remains unique without sacrificing
    determinism across re-parses of the same input.

    The caller should supply a :class:`NodeIdContext` when IDs belong to one
    parse session.  Omitting it performs a stateless single-ID calculation and
    is useful for deterministic helpers, but cannot resolve collisions across
    multiple calls.

    Args:
        module_path: Source module/rule path
        rule_name: Line type (e.g. "VALUE_CONCLUSION")
        variable_name: The node's variable name
        normalized_text: Stripped/lowered node text for identity
        parent_module_path: Parent rule/module path (empty for root nodes)
        import_namespace: Versioned package (e.g. "common_rules@2.1.0");
            empty string for local nodes
        line_number: **Deprecated** — retained for backward compatibility only.
            New code must not pass this parameter.
    """
    if line_number is not None:
        warnings.warn(
            "line_number is deprecated in generate_node_id(); "
            "use normalized_text + import_namespace instead",
            DeprecationWarning,
            stacklevel=2,
        )
    active_context = context if context is not None else NodeIdContext()
    return active_context.generate_node_id(
        module_path=module_path,
        rule_name=rule_name,
        variable_name=variable_name,
        normalized_text=normalized_text,
        parent_module_path=parent_module_path,
        import_namespace=import_namespace,
        line_number=line_number,
    )


def generate_node_id_legacy(
    module_path: str, rule_name: str, line_number: int, variable_name: str
) -> str:
    """Legacy signature preserved for backward compatibility.

    Produces the same hash as the old ``generate_node_id(module_path, rule_name,
    line_number, variable_name)`` signature. New code should call
    ``generate_node_id()`` with the new parameters instead.
    """
    return generate_node_id(
        module_path=module_path,
        rule_name=rule_name,
        variable_name=variable_name,
        normalized_text="",
        parent_module_path="",
        import_namespace="",
        line_number=line_number,
    )


def reset_parse_context(context: NodeIdContext) -> None:
    """Clear an explicitly supplied parse context."""
    context.reset()


def validate_no_existing_collisions(
    persisted_session_ids: Set[str],
    *,
    context: NodeIdContext,
) -> None:
    """Raise when an explicit context overlaps caller-supplied persisted IDs."""
    context.validate_no_existing_collisions(persisted_session_ids)
