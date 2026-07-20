"""Enforce the deterministic dependency boundary of the current Core slice."""

import ast
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "inferra_core"
ALLOWED_THIRD_PARTY_IMPORTS = set()
FORBIDDEN_IMPORTS = {
    "celery",
    "fastapi",
    "httpx",
    "openai",
    "rdflib",
    "redis",
    "requests",
    "sqlalchemy",
    "structlog",
}
FORBIDDEN_HOST_STDLIB_IMPORTS = {
    "concurrent",
    "logging",
    "os",
    "pathlib",
    "random",
    "secrets",
    "socket",
    "subprocess",
    "threading",
    "time",
    "urllib",
    "uuid",
}


def test_core_slice_uses_only_reviewed_dependencies() -> None:
    violations = []

    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = {node.module.split(".", 1)[0]}
            else:
                continue

            for root in roots:
                if (
                    root not in sys.stdlib_module_names
                    and root not in ALLOWED_THIRD_PARTY_IMPORTS
                    and root not in {"__future__", "inferra_core"}
                ):
                    violations.append(f"{path.relative_to(PACKAGE_ROOT)} imports {root}")

    assert violations == []


def test_core_never_imports_framework_or_runtime_dependencies() -> None:
    violations = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.split(".", 1)[0]}
            else:
                continue
            for root in roots & FORBIDDEN_IMPORTS:
                violations.append(f"{path.relative_to(PACKAGE_ROOT)} imports {root}")
    assert violations == []


def test_core_has_no_implicit_host_state_or_io_imports() -> None:
    violations = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.split(".", 1)[0]}
            else:
                continue
            for root in roots & FORBIDDEN_HOST_STDLIB_IMPORTS:
                violations.append(f"{path.relative_to(PACKAGE_ROOT)} imports {root}")
    assert violations == []


def test_core_package_never_mentions_the_platform_namespace() -> None:
    offenders = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = {node.module}
            else:
                continue
            if any(module == "src" or module.startswith("src.") for module in modules):
                offenders.append(str(path.relative_to(PACKAGE_ROOT)))
                break

    assert offenders == []


def test_core_never_delegates_rule_source_to_dynamic_evaluation() -> None:
    violations = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id in {
                "compile",
                "eval",
                "exec",
            }:
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT)} calls {node.func.id}"
                )
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "parse_expr",
                "sympify",
            }:
                violations.append(
                    f"{path.relative_to(PACKAGE_ROOT)} calls {node.func.attr}"
                )

    assert violations == []
