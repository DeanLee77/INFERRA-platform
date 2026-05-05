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
        "src/domain/nodes/node_set.py",
        "src/domain/graph/matrix_to_hyper_adapter.py",
        "src/domain/graph/graph_to_matrix_adapter.py",
        "src/domain/rule_parser/rule_set_parser.py",
        "src/domain/rule_parser/i_scan_feeder.py",
    }
)

_LEGACY_DVDM_IMPORT_WHITELIST: FrozenSet[str] = frozenset()

_LEGACY_DEP_BUILDER_IMPORT_WHITELIST: FrozenSet[str] = frozenset()

_LEGACY_GET_NODE_ID_WHITELIST: FrozenSet[str] = frozenset(
    {
        "src/domain/inference/topo_sort.py",
    }
)

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
