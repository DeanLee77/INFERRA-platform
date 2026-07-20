"""Executable P0.1 inventory and Core-boundary baseline.

The manifest deliberately records the current extraction debt. Removing a
known crossing is welcome, but requires an intentional manifest update so the
baseline cannot drift silently in either direction.
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set, Tuple


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _REPO_ROOT / "src"
_MANIFEST_PATH = _REPO_ROOT / "docs" / "evaluation" / "core_boundary_inventory.json"
_VALID_CLASSIFICATIONS = {
    "core_initial",
    "platform_runtime",
    "platform_compatibility",
    "extension",
}
_FORBIDDEN_CORE_IMPORT_ROOTS = {
    "celery",
    "dotenv",
    "fastapi",
    "openai",
    "pydantic",
    "pydantic_settings",
    "psycopg2",
    "redis",
    "requests",
    "sqlalchemy",
    "uvicorn",
}


def _load_manifest() -> Dict[str, Any]:
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


def _production_python_files() -> Iterable[Path]:
    return sorted(_SRC_ROOT.rglob("*.py"))


def _relative(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def _classification(path: str, manifest: Dict[str, Any]) -> Optional[str]:
    exact = manifest["exact_rules"].get(path)
    if exact is not None:
        return exact

    matches = [
        (prefix, classification)
        for prefix, classification in manifest["prefix_rules"].items()
        if path.startswith(prefix)
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: len(item[0]))[1]


def _module_for_path(path: Path) -> str:
    relative = path.relative_to(_REPO_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_relative_import(path: Path, node: ast.ImportFrom) -> Optional[str]:
    current_module = _module_for_path(path)
    package_parts = current_module.split(".")
    if path.name != "__init__.py":
        package_parts.pop()
    levels_up = max(node.level - 1, 0)
    if levels_up > len(package_parts):
        return None
    base = package_parts[: len(package_parts) - levels_up]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def _imported_modules(path: Path) -> Set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                module = _resolve_relative_import(path, node)
            else:
                module = node.module
            if module:
                modules.add(module)
    return modules


def _module_path(module: str) -> Optional[Path]:
    base = _REPO_ROOT.joinpath(*module.split("."))
    module_file = base.with_suffix(".py")
    if module_file.is_file():
        return module_file
    package_file = base / "__init__.py"
    if package_file.is_file():
        return package_file
    return None


def _core_boundary_imports(manifest: Dict[str, Any]) -> list[Dict[str, str]]:
    crossings: Set[Tuple[str, str, str]] = set()
    for path in _production_python_files():
        importer = _relative(path)
        if _classification(importer, manifest) != "core_initial":
            continue
        for imported_module in _imported_modules(path):
            if not imported_module.startswith("src"):
                continue
            target = _module_path(imported_module)
            if target is None:
                continue
            target_classification = _classification(_relative(target), manifest)
            if target_classification != "core_initial":
                crossings.add((importer, imported_module, str(target_classification)))
    return [
        {
            "importer": importer,
            "imported_module": imported_module,
            "target_classification": target_classification,
        }
        for importer, imported_module, target_classification in sorted(crossings)
    ]


def _core_third_party_imports(manifest: Dict[str, Any]) -> list[Dict[str, Any]]:
    importers_by_root: Dict[str, Set[str]] = {}
    for path in _production_python_files():
        importer = _relative(path)
        if _classification(importer, manifest) != "core_initial":
            continue
        for module in _imported_modules(path):
            root = module.split(".", 1)[0]
            if root in sys.stdlib_module_names or root in {
                "__future__",
                "inferra_core",
                "src",
            }:
                continue
            importers_by_root.setdefault(root, set()).add(importer)
    return [
        {"module": module, "importers": sorted(importers)}
        for module, importers in sorted(importers_by_root.items())
    ]


def test_every_production_python_module_is_classified() -> None:
    manifest = _load_manifest()
    invalid_rules = {
        path: classification
        for path, classification in manifest["exact_rules"].items()
        if classification not in _VALID_CLASSIFICATIONS
    }
    invalid_rules.update(
        {
            prefix: classification
            for prefix, classification in manifest["prefix_rules"].items()
            if classification not in _VALID_CLASSIFICATIONS
        }
    )
    assert not invalid_rules, f"Unknown classifications: {invalid_rules}"

    files = list(_production_python_files())
    unclassified = [
        _relative(path)
        for path in files
        if _classification(_relative(path), manifest) is None
    ]
    assert not unclassified, "Unclassified production modules:\n" + "\n".join(unclassified)
    assert len(files) == manifest["baseline"]["python_module_count"]
    actual_counts = Counter(
        _classification(_relative(path), manifest) for path in files
    )
    assert dict(actual_counts) == manifest["classification_counts"]


def test_known_core_boundary_imports_have_not_drifted() -> None:
    manifest = _load_manifest()
    actual = _core_boundary_imports(manifest)
    expected = manifest["known_core_boundary_imports"]
    assert actual == expected, (
        "Core boundary imports changed. Review the change and update the P0.1 "
        "manifest intentionally. Actual crossings:\n"
        + json.dumps(actual, indent=2)
    )


def test_core_has_no_framework_or_data_service_imports() -> None:
    manifest = _load_manifest()
    violations: list[Tuple[str, str]] = []
    for path in _production_python_files():
        relative = _relative(path)
        if _classification(relative, manifest) != "core_initial":
            continue
        for module in _imported_modules(path):
            root = module.split(".", 1)[0]
            if root in _FORBIDDEN_CORE_IMPORT_ROOTS:
                violations.append((relative, module))
    assert not violations, "Forbidden Core dependencies:\n" + "\n".join(
        f"{path}: {module}" for path, module in sorted(violations)
    )


def test_known_core_third_party_imports_have_not_drifted() -> None:
    manifest = _load_manifest()
    assert _core_third_party_imports(manifest) == manifest[
        "known_core_third_party_imports"
    ]
    assert any(
        entry["module"] == "sympy"
        for entry in manifest["baseline_known_core_third_party_imports"]
    )
    assert all(
        entry["module"] != "sympy"
        for entry in manifest["known_core_third_party_imports"]
    )


def test_recorded_blockers_are_unique_and_actionable() -> None:
    blockers = _load_manifest()["known_extraction_blockers"]
    ids = [blocker["id"] for blocker in blockers]
    assert len(ids) == len(set(ids))
    assert all(blocker["scope"] and blocker["required_action"] for blocker in blockers)


def test_rule_syntax_reference_preserves_baseline_and_current_contract() -> None:
    manifest = _load_manifest()
    baseline = manifest["baseline"]
    assert baseline["rule_syntax_version"] == "0.3"
    assert baseline["rule_syntax_dictionary_sha256"] == (
        "388919ff8f36ac198ab92d04e8279e2b19c948754e86eb649e557bf05cf2c9c7"
    )

    current = manifest["current_contract"]
    dictionary = _REPO_ROOT / current["rule_syntax_dictionary"]
    assert current["rule_syntax_version"] == "0.3.1"
    assert hashlib.sha256(dictionary.read_bytes()).hexdigest() == current[
        "rule_syntax_dictionary_sha256"
    ]
