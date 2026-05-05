import time
from typing import Any, Dict, Iterable, List, Set

import structlog

from src.domain.graph.dependency_type import DependencyType
from src.ports.abduction_port import AbductionPort

log = structlog.get_logger(__name__)


class Z3AbductionAdapter(AbductionPort):
    """Bounded Z3-backed abduction over a primitive graph snapshot."""

    DEFAULT_TIMEOUT_MS = 2000
    DEFAULT_MAX_MODELS = 50
    DEFAULT_DEPTH_GUARD = 25

    def __init__(
        self,
        *,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        max_models: int = DEFAULT_MAX_MODELS,
        depth_guard: int = DEFAULT_DEPTH_GUARD,
    ) -> None:
        self.timeout_ms = timeout_ms
        self.max_models = max_models
        self.depth_guard = depth_guard

    def propose_hypotheses(
        self,
        target: str,
        working_memory: Dict[str, Any],
        graph_snapshot: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        start = time.perf_counter()
        try:
            from z3 import Bool, BoolVal, Solver, is_true, sat
        except ImportError:
            log.warning(
                "z3_not_installed",
                session_id="",
                node_id=target,
                fact_source="",
                correlation_id="",
            )
            return []

        if self._known_bool(working_memory.get(target)) is True:
            return []

        child_groups = graph_snapshot.get("child_groups", {})
        candidates = self._candidate_leaves(target, child_groups, working_memory)
        hypotheses: List[Dict[str, Any]] = []

        for candidate in candidates[: self.max_models]:
            variables: Dict[str, Any] = {}

            def expr(name: str, depth: int = 0, visiting: Set[str] | None = None):
                visiting = visiting or set()
                if depth > self.depth_guard or name in visiting:
                    return Bool(name)
                known = self._known_bool(working_memory.get(name))
                if known is not None:
                    return BoolVal(known)
                if name == candidate:
                    return BoolVal(True)
                groups = child_groups.get(name) or []
                if not groups:
                    variables.setdefault(name, Bool(name))
                    return variables[name]
                visiting.add(name)
                group_exprs = []
                for dep_type_int, children in groups:
                    child_exprs = [expr(child, depth + 1, set(visiting)) for child in children]
                    if not child_exprs:
                        continue
                    dep_type = DependencyType(dep_type_int)
                    if dep_type & DependencyType.OR:
                        from z3 import Or

                        group_exprs.append(Or(*child_exprs))
                    else:
                        from z3 import And

                        group_exprs.append(And(*child_exprs))
                if not group_exprs:
                    variables.setdefault(name, Bool(name))
                    return variables[name]
                if len(group_exprs) == 1:
                    return group_exprs[0]
                from z3 import And

                return And(*group_exprs)

            solver = Solver()
            solver.set("timeout", self.timeout_ms)
            solver.add(expr(target) == BoolVal(True))
            outcome = solver.check()
            if outcome == sat and is_true(solver.model().eval(expr(target), model_completion=True)):
                hypotheses.append(
                    {
                        "fact_name": candidate,
                        "suggested_value": "true",
                        "confidence": self._confidence_for(candidate, target, child_groups),
                        "dependency_path": self._path_to(target, candidate, child_groups),
                        "ontology_consistent": True,
                    }
                )

        hypotheses.sort(key=lambda item: (-item["confidence"], item["fact_name"]))
        log.info(
            "abduction_propose_complete",
            session_id="",
            node_id=target,
            fact_source="HYPOTHETICAL",
            correlation_id="",
            hypothesis_count=len(hypotheses),
            solver_time_ms=round((time.perf_counter() - start) * 1000, 2),
        )
        return hypotheses[: self.max_models]

    def _candidate_leaves(
        self,
        target: str,
        child_groups: Dict[str, Iterable],
        working_memory: Dict[str, Any],
    ) -> List[str]:
        leaves: Set[str] = set()

        def walk(name: str, depth: int = 0, seen: Set[str] | None = None) -> None:
            seen = seen or set()
            if depth > self.depth_guard or name in seen:
                return
            seen.add(name)
            groups = child_groups.get(name) or []
            if not groups:
                if self._known_bool(working_memory.get(name)) is None:
                    leaves.add(name)
                return
            for _, children in groups:
                for child in children:
                    walk(child, depth + 1, set(seen))

        walk(target)
        leaves.discard(target)
        return sorted(leaves)

    def _path_to(
        self,
        target: str,
        candidate: str,
        child_groups: Dict[str, Iterable],
    ) -> List[str]:
        stack: List[tuple[str, List[str]]] = [(target, [target])]
        seen: Set[str] = set()
        while stack:
            current, path = stack.pop()
            if current == candidate:
                return path
            if current in seen:
                continue
            seen.add(current)
            for _, children in child_groups.get(current) or []:
                for child in children:
                    stack.append((child, [*path, child]))
        return [candidate]

    def _confidence_for(
        self,
        candidate: str,
        target: str,
        child_groups: Dict[str, Iterable],
    ) -> float:
        path_len = max(len(self._path_to(target, candidate, child_groups)), 1)
        return max(0.5, round(0.9 - (path_len - 2) * 0.05, 2))

    @staticmethod
    def _known_bool(value: Any) -> bool | None:
        if hasattr(value, "get_value"):
            value = value.get_value()
        if isinstance(value, bool):
            return value
        return None
