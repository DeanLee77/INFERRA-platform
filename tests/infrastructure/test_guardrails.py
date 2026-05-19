"""
Phase 2.5 Guardrails — Boundary checks for DependencyMatrix and node_id usage.

These tests enforce that new production code does NOT import legacy
matrix classes or use deprecated node_id (integer) APIs.  Existing
legacy consumers are whitelisted and will be removed as WS-1 through
WS-8 migrate them to graph-native alternatives.
"""

import ast
import os
from pathlib import Path
from typing import FrozenSet, Set

import pytest

_SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src"

_LEGACY_MATRIX_IMPORT_WHITELIST: FrozenSet[str] = frozenset(
    {
        "src/domain/graph/matrix_to_hyper_adapter.py",
        "src/domain/graph/graph_to_matrix_adapter.py",
        "src/domain/graph/__init__.py",
        "src/domain/nodes/dependency_matrix.py",
    }
)

_LEGACY_DVDM_IMPORT_WHITELIST: FrozenSet[str] = frozenset()

_LEGACY_DEP_BUILDER_IMPORT_WHITELIST: FrozenSet[str] = frozenset()

_LEGACY_GET_NODE_ID_WHITELIST: FrozenSet[str] = frozenset()

_FORBIDDEN_MATRIX_SYMBOLS = (
    "DependencyMatrix",
    "DynamicVectorisedDependencyMatrix",
    "DependencyBuilder",
)


def _collect_py_files(root: Path) -> list:
    py_files: list = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".py"):
                py_files.append(Path(dirpath) / fn)
    return py_files


def _read_imports_and_calls(filepath: Path) -> tuple:
    source = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return set(), set()

    imported_symbols: Set[str] = set()
    called_attrs: Set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_symbols.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    imported_symbols.add(alias.asname)
                else:
                    name = alias.name.split(".")[-1]
                    imported_symbols.add(name)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "get_node_id":
                called_attrs.add("get_node_id")

    return imported_symbols, called_attrs


def _read_import_modules(filepath: Path) -> Set[str]:
    source = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return set()

    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)

    return modules


def _rel_path(filepath: Path) -> str:
    parts = filepath.parts
    src_idx = parts.index("src")
    return str(Path(*parts[src_idx:])).replace(os.sep, "/")


class TestMatrixImportGuardrails:
    """No new production code may import DependencyMatrix."""

    def test_no_new_dependency_matrix_imports(self):
        violations: list = []
        for filepath in _collect_py_files(_SRC_ROOT):
            rel = _rel_path(filepath)
            imported, _ = _read_imports_and_calls(filepath)
            if "DependencyMatrix" in imported and rel not in _LEGACY_MATRIX_IMPORT_WHITELIST:
                violations.append(rel)
        assert not violations, (
            "DependencyMatrix imported in new production files (not in whitelist):\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nIf this is a sanctioned legacy consumer, add it to "
            "_LEGACY_MATRIX_IMPORT_WHITELIST in test_guardrails.py."
        )

    def test_no_new_dynamic_vectorised_dependency_matrix_imports(self):
        violations: list = []
        for filepath in _collect_py_files(_SRC_ROOT):
            rel = _rel_path(filepath)
            imported, _ = _read_imports_and_calls(filepath)
            if "DynamicVectorisedDependencyMatrix" in imported and rel not in _LEGACY_DVDM_IMPORT_WHITELIST:
                violations.append(rel)
        assert not violations, (
            "DynamicVectorisedDependencyMatrix imported in new production files (not in whitelist):\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nIf this is a sanctioned legacy consumer, add it to "
            "_LEGACY_DVDM_IMPORT_WHITELIST in test_guardrails.py."
        )

    def test_no_new_dependency_builder_imports(self):
        violations: list = []
        for filepath in _collect_py_files(_SRC_ROOT):
            rel = _rel_path(filepath)
            imported, _ = _read_imports_and_calls(filepath)
            if "DependencyBuilder" in imported and rel not in _LEGACY_DEP_BUILDER_IMPORT_WHITELIST:
                violations.append(rel)
        assert not violations, (
            "DependencyBuilder imported in new production files (not in whitelist):\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nIf this is a sanctioned legacy consumer, add it to "
            "_LEGACY_DEP_BUILDER_IMPORT_WHITELIST in test_guardrails.py."
        )


class TestNodeIdUsageGuardrails:
    """No new production code may call get_node_id() — use get_stable_node_id() or get_node_name()."""

    def test_no_new_get_node_id_calls(self):
        violations: list = []
        for filepath in _collect_py_files(_SRC_ROOT):
            rel = _rel_path(filepath)
            _, called = _read_imports_and_calls(filepath)
            if "get_node_id" in called and rel not in _LEGACY_GET_NODE_ID_WHITELIST:
                violations.append(rel)
        assert not violations, (
            "get_node_id() called in new production files (not in whitelist):\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nUse get_stable_node_id() or get_node_name() instead. "
            "If this is a sanctioned legacy consumer, add it to "
            "_LEGACY_GET_NODE_ID_WHITELIST in test_guardrails.py."
        )

    def test_iterate_line_subgraph_extraction_has_no_runtime_node_id_dictionary(self):
        source = (_SRC_ROOT / "domain" / "nodes" / "iterate_line.py").read_text(
            encoding="utf-8"
        )
        forbidden = (
            "node_id_dictionary",
            "_get_next_iterate_node_id",
            "get_node_id(",
        )
        violations = [token for token in forbidden if token in source]

        assert not violations, (
            "IterateLine subgraph extraction must stay graph-name-keyed. "
            "Forbidden runtime node-id tokens found: "
            + ", ".join(violations)
        )

    def test_rule_set_scanner_establishes_graph_without_matrix_setter(self):
        source = (_SRC_ROOT / "domain" / "rule_parser" / "rule_set_scanner.py").read_text(
            encoding="utf-8"
        )

        assert "create_dependency_graph()" in source
        assert "set_dependency_matrix(" not in source

    def test_topo_sort_facade_has_no_private_matrix_algorithms(self):
        source = (_SRC_ROOT / "domain" / "inference" / "topo_sort.py").read_text(
            encoding="utf-8"
        )
        forbidden = (
            "_create_copy_of_dependency_matrix",
            "_count_incoming_edges",
            "_get_child_ids",
            "_check_for_cycles",
            "_deepening",
            "_visit(",
        )
        violations = [token for token in forbidden if token in source]

        assert not violations, (
            "topo_sort.py must stay a graph adapter facade. "
            "Private matrix algorithms found: "
            + ", ".join(violations)
        )


class TestWhitelistSanity:
    """Ensure whitelisted files still exist and still use the legacy API."""

    @pytest.mark.parametrize(
        "filepath",
        list(_LEGACY_MATRIX_IMPORT_WHITELIST),
        ids=list(_LEGACY_MATRIX_IMPORT_WHITELIST),
    )
    def test_matrix_whitelist_entries_still_import_dependency_matrix(self, filepath):
        full = _SRC_ROOT.parent / filepath
        if not full.exists():
            pytest.skip(f"{filepath} no longer exists (likely migrated)")
        imported, _ = _read_imports_and_calls(full)
        assert "DependencyMatrix" in imported, (
            f"{filepath} is whitelisted for DependencyMatrix but no longer imports it. "
            "Remove it from _LEGACY_MATRIX_IMPORT_WHITELIST."
        )

    @pytest.mark.parametrize(
        "filepath",
        list(_LEGACY_DVDM_IMPORT_WHITELIST),
        ids=list(_LEGACY_DVDM_IMPORT_WHITELIST),
    )
    def test_dvdm_whitelist_entries_still_import_dvdm(self, filepath):
        full = _SRC_ROOT.parent / filepath
        if not full.exists():
            pytest.skip(f"{filepath} no longer exists (likely migrated)")
        imported, _ = _read_imports_and_calls(full)
        assert "DynamicVectorisedDependencyMatrix" in imported, (
            f"{filepath} is whitelisted for DynamicVectorisedDependencyMatrix but no longer imports it. "
            "Remove it from _LEGACY_DVDM_IMPORT_WHITELIST."
        )

    @pytest.mark.parametrize(
        "filepath",
        list(_LEGACY_DEP_BUILDER_IMPORT_WHITELIST),
        ids=list(_LEGACY_DEP_BUILDER_IMPORT_WHITELIST),
    )
    def test_builder_whitelist_entries_still_import_dependency_builder(self, filepath):
        full = _SRC_ROOT.parent / filepath
        if not full.exists():
            pytest.skip(f"{filepath} no longer exists (likely migrated)")
        imported, _ = _read_imports_and_calls(full)
        assert "DependencyBuilder" in imported, (
            f"{filepath} is whitelisted for DependencyBuilder but no longer imports it. "
            "Remove it from _LEGACY_DEP_BUILDER_IMPORT_WHITELIST."
        )

    @pytest.mark.parametrize(
        "filepath",
        list(_LEGACY_GET_NODE_ID_WHITELIST),
        ids=list(_LEGACY_GET_NODE_ID_WHITELIST),
    )
    def test_node_id_whitelist_entries_still_call_get_node_id(self, filepath):
        full = _SRC_ROOT.parent / filepath
        if not full.exists():
            pytest.skip(f"{filepath} no longer exists (likely migrated)")
        _, called = _read_imports_and_calls(full)
        assert "get_node_id" in called, (
            f"{filepath} is whitelisted for get_node_id() but no longer calls it. "
            "Remove it from _LEGACY_GET_NODE_ID_WHITELIST."
        )


class TestArchitectureBoundaryImports:
    """Keep Bucket 2 restructuring boundaries from drifting back."""

    def test_no_production_imports_from_removed_shared_package(self):
        violations: list = []
        for filepath in _collect_py_files(_SRC_ROOT):
            rel = _rel_path(filepath)
            modules = _read_import_modules(filepath)
            if any(module == "src.shared" or module.startswith("src.shared.") for module in modules):
                violations.append(rel)

        assert not violations, (
            "Production code imports from removed src.shared package:\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nMove shared-looking symbols to their owning domain or infrastructure package."
        )

    def test_no_production_imports_from_removed_top_level_schemas_or_dependencies(self):
        violations: list = []
        removed_roots = ("src.schemas", "src.dependencies")
        for filepath in _collect_py_files(_SRC_ROOT):
            rel = _rel_path(filepath)
            modules = _read_import_modules(filepath)
            if any(module == root or module.startswith(f"{root}.") for module in modules for root in removed_roots):
                violations.append(rel)

        assert not violations, (
            "Production code imports removed top-level HTTP shims:\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nUse src.adapters.inbound.http.schemas or "
            "src.adapters.inbound.http.dependencies instead."
        )

    def test_no_legacy_logger_imports(self):
        violations: list = []
        for filepath in _collect_py_files(_SRC_ROOT):
            rel = _rel_path(filepath)
            modules = _read_import_modules(filepath)
            if "src.infrastructure.legacy_logger" in modules:
                violations.append(rel)

        assert not violations, (
            "Production code imports src.infrastructure.legacy_logger:\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nUse src.infrastructure.logging_config.get_logger instead."
        )

    def test_no_bare_stdlib_logging_outside_logging_config(self):
        violations: list = []
        allowed = {"src/infrastructure/logging_config.py"}
        for filepath in _collect_py_files(_SRC_ROOT):
            rel = _rel_path(filepath)
            modules = _read_import_modules(filepath)
            if "logging" in modules and rel not in allowed:
                violations.append(rel)

        assert not violations, (
            "Production code imports bare stdlib logging outside logging_config:\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nUse structlog via src.infrastructure.logging_config.get_logger."
        )

    def test_no_production_imports_from_legacy_node_graph_modules(self):
        violations: list = []
        legacy_modules = {
            "src.domain.nodes.dependency",
            "src.domain.nodes.dependency_matrix",
            "src.domain.nodes.dependency_type",
        }
        shim_files = {
            "src/domain/nodes/dependency.py",
            "src/domain/nodes/dependency_matrix.py",
            "src/domain/nodes/dependency_type.py",
        }

        for filepath in _collect_py_files(_SRC_ROOT):
            rel = _rel_path(filepath)
            if rel in shim_files:
                continue
            modules = _read_import_modules(filepath)
            if legacy_modules.intersection(modules):
                violations.append(rel)

        assert not violations, (
            "Production code imports graph concerns from src.domain.nodes:\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nUse src.domain.graph.dependency, dependency_matrix, or "
            "dependency_type instead."
        )
