import hashlib
import threading
import warnings
from typing import Dict, Optional, Set


class _ParseContext:
    """Per-session collision tracker for deterministic node ID generation.

    Thread-safe: each session owns its own context, avoiding cross-session
    contamination from the previous module-level global dict.
    """

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


_local: threading.local = threading.local()


def _get_context() -> _ParseContext:
    if not hasattr(_local, "parse_context"):
        _local.parse_context = _ParseContext()
    return _local.parse_context


def generate_node_id(
    module_path: str,
    rule_name: str,
    variable_name: str = "",
    normalized_text: str = "",
    parent_module_path: str = "",
    import_namespace: str = "",
    line_number: Optional[int] = None,
) -> str:
    """Deterministic 16-char hex ID (64-bit entropy).

    Same inputs always return the same ID within a parse session. Two distinct
    inputs that share the same 16-char SHA-256 prefix get a monotonic counter
    suffix appended so node identity remains unique without sacrificing
    determinism across re-parses of the same input.

    Thread-safe: each thread maintains its own collision tracker via
    threading.local, so concurrent parses never corrupt each other.

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
    return _get_context().generate_node_id(
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


def reset_parse_context() -> None:
    """Clear active IDs. Call at the start of each RuleSetParser.scan() to isolate sessions."""
    _get_context().reset()


def validate_no_existing_collisions(persisted_session_ids: Set[str]) -> None:
    """Start-up guard: raises ValueError if any newly-generated ID overlaps a persisted session."""
    _get_context().validate_no_existing_collisions(persisted_session_ids)
